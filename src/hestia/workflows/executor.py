"""Workflow executor: topological DAG walker with trust enforcement."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hestia.app import AppContext
from hestia.core.types import ChatResponse, Message
from hestia.tools.capabilities import (
    EMAIL_SEND,
    MEMORY_READ,
    MEMORY_WRITE,
    NETWORK_EGRESS,
    SELF_MANAGEMENT,
    SHELL_EXEC,
    WRITE_LOCAL,
)
from hestia.workflows.models import ExecutionResult, NodeResult, WorkflowEdge, WorkflowNode
from hestia.workflows.store import WorkflowStore

if TYPE_CHECKING:
    from hestia.workflows.execution_store import ExecutionStore

logger = logging.getLogger(__name__)

_TRUST_CAPS: dict[str, set[str]] = {
    "paranoid": set(),
    "household": {MEMORY_READ, MEMORY_WRITE, WRITE_LOCAL},
    "developer": {
        MEMORY_READ,
        MEMORY_WRITE,
        WRITE_LOCAL,
        SHELL_EXEC,
        NETWORK_EGRESS,
        EMAIL_SEND,
        SELF_MANAGEMENT,
    },
}


def _blocked_capabilities(trust_level: str) -> set[str]:
    """Return the set of capabilities blocked for a given trust level."""
    allowed = _TRUST_CAPS.get(trust_level, set())
    all_caps = {
        MEMORY_READ,
        MEMORY_WRITE,
        WRITE_LOCAL,
        SHELL_EXEC,
        NETWORK_EGRESS,
        EMAIL_SEND,
        SELF_MANAGEMENT,
    }
    return all_caps - allowed


def _topological_sort(
    nodes: list[WorkflowNode], edges: list[WorkflowEdge]
) -> list[WorkflowNode]:
    """Return nodes in topological order (dependencies first).

    Raises:
        ValueError: If the graph contains a cycle.
    """
    node_map = {n.id: n for n in nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in nodes}

    for edge in edges:
        if edge.source_node_id in adj and edge.target_node_id in in_degree:
            adj[edge.source_node_id].append(edge.target_node_id)
            in_degree[edge.target_node_id] += 1

    queue = deque(n_id for n_id, deg in in_degree.items() if deg == 0)
    result: list[WorkflowNode] = []

    while queue:
        n_id = queue.popleft()
        result.append(node_map[n_id])
        for target_id in adj[n_id]:
            in_degree[target_id] -= 1
            if in_degree[target_id] == 0:
                queue.append(target_id)

    if len(result) != len(nodes):
        raise ValueError("Workflow graph contains a cycle")

    return result


def _resolve_inputs(
    node: WorkflowNode,
    edges: list[WorkflowEdge],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """Resolve node inputs from upstream node outputs and node config.

    Upstream outputs are keyed by target_handle when present, otherwise by
    source_node_id. Node config is merged on top as defaults.
    """
    inputs: dict[str, Any] = dict(node.config)
    for edge in edges:
        if edge.target_node_id != node.id:
            continue
        source_output = outputs.get(edge.source_node_id)
        key = edge.target_handle or edge.source_node_id
        if key is not None:
            inputs[key] = source_output
    return inputs


@dataclass
class _NodeOutput:
    """Internal wrapper for node execution output with token usage."""

    value: Any
    prompt_tokens: int = 0
    completion_tokens: int = 0


class WorkflowExecutor:
    """Executes workflow DAGs with topological ordering and trust enforcement.

    Args:
        app: The application context providing inference, tool registry, and adapters.
    """

    def __init__(
        self,
        app: AppContext,
        workflow_store: WorkflowStore | None = None,
        execution_store: ExecutionStore | None = None,
    ) -> None:
        self._app = app
        self._workflow_store = workflow_store
        self._execution_store = execution_store

    async def execute(self, workflow_id: str, trigger_payload: Any) -> ExecutionResult:
        """Execute a workflow by its ID.

        Loads the workflow and its active version, topologically sorts the nodes,
        and executes them in dependency order with trust checks and fail-fast
        semantics.

        Args:
            workflow_id: The unique identifier of the workflow.
            trigger_payload: The payload that triggered the workflow execution.

        Returns:
            ExecutionResult containing the status and results of all nodes.
        """
        started_at = time.perf_counter()
        store = self._workflow_store or WorkflowStore(self._app.db)
        workflow = await store.get_workflow(workflow_id)
        if workflow is None:
            result = ExecutionResult(
                workflow_id=workflow_id,
                status="failed",
                node_results=[
                    NodeResult(
                        node_id="",
                        status="failed",
                        error=f"Workflow not found: {workflow_id}",
                    )
                ],
            )
            if self._execution_store is not None:
                await self._execution_store.save_execution(
                    result, workflow_id, 0, trigger_payload
                )
            return result

        version = await store.get_active_version(workflow_id)
        if version is None:
            result = ExecutionResult(
                workflow_id=workflow_id,
                status="failed",
                node_results=[
                    NodeResult(
                        node_id="",
                        status="failed",
                        error=f"No active version for workflow: {workflow_id}",
                    )
                ],
            )
            if self._execution_store is not None:
                await self._execution_store.save_execution(
                    result, workflow_id, 0, trigger_payload
                )
            return result

        node_results: list[NodeResult] = []
        outputs: dict[str, Any] = {"trigger": trigger_payload}
        total_prompt_tokens = 0
        total_completion_tokens = 0

        try:
            order = _topological_sort(version.nodes, version.edges)
        except ValueError as exc:
            result = ExecutionResult(
                workflow_id=workflow_id,
                status="failed",
                node_results=[
                    NodeResult(
                        node_id="",
                        status="failed",
                        error=f"Invalid workflow graph: {exc}",
                    )
                ],
            )
            if self._execution_store is not None:
                await self._execution_store.save_execution(
                    result, workflow_id, version.version, trigger_payload
                )
            return result

        blocked = _blocked_capabilities(workflow.trust_level)
        active_edges: set[str] = set()

        for node in order:
            incoming = [e for e in version.edges if e.target_node_id == node.id]
            if incoming and not any(e.id in active_edges for e in incoming):
                continue

            node_caps = set(node.capabilities)
            denied = node_caps & blocked
            if denied:
                nr = NodeResult(
                    node_id=node.id,
                    status="failed",
                    error=(
                        f"Trust level '{workflow.trust_level}' denies "
                        f"capabilities: {', '.join(sorted(denied))}"
                    ),
                )
                node_results.append(nr)
                result = ExecutionResult(
                    workflow_id=workflow_id,
                    status="failed",
                    node_results=node_results,
                    outputs=outputs,
                )
                if self._execution_store is not None:
                    await self._execution_store.save_execution(
                        result, workflow_id, version.version, trigger_payload
                    )
                return result

            inputs = _resolve_inputs(node, version.edges, outputs)

            # Seed root nodes (no incoming edges) with the trigger payload
            has_upstream = any(e.target_node_id == node.id for e in version.edges)
            if not has_upstream:
                if isinstance(trigger_payload, dict):
                    inputs = {**trigger_payload, **inputs}
                else:
                    inputs["trigger"] = trigger_payload

            node_start = time.perf_counter()
            try:
                node_output = await self._run_node(node, inputs)
            except Exception as exc:
                logger.exception("Node %s failed in workflow %s", node.id, workflow_id)
                elapsed_ms = int((time.perf_counter() - node_start) * 1000)
                nr = NodeResult(
                    node_id=node.id,
                    status="failed",
                    error=str(exc),
                    elapsed_ms=elapsed_ms,
                )
                node_results.append(nr)
                result = ExecutionResult(
                    workflow_id=workflow_id,
                    status="failed",
                    node_results=node_results,
                    outputs=outputs,
                )
                if self._execution_store is not None:
                    await self._execution_store.save_execution(
                        result, workflow_id, version.version, trigger_payload
                    )
                return result

            elapsed_ms = int((time.perf_counter() - node_start) * 1000)
            nr = NodeResult(
                node_id=node.id,
                status="ok",
                output=node_output.value,
                elapsed_ms=elapsed_ms,
                prompt_tokens=node_output.prompt_tokens,
                completion_tokens=node_output.completion_tokens,
            )
            node_results.append(nr)
            outputs[node.id] = node_output.value
            total_prompt_tokens += node_output.prompt_tokens
            total_completion_tokens += node_output.completion_tokens

            for edge in version.edges:
                if edge.source_node_id != node.id:
                    continue
                if node.type == "condition":
                    if (
                        node_output.value
                        and edge.source_handle == "true"
                    ) or (
                        not node_output.value
                        and edge.source_handle == "false"
                    ):
                        active_edges.add(edge.id)
                elif node.type == "llm_decision":
                    if edge.source_handle == str(node_output.value):
                        active_edges.add(edge.id)
                else:
                    active_edges.add(edge.id)

        total_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        result = ExecutionResult(
            workflow_id=workflow_id,
            status="ok",
            node_results=node_results,
            outputs=outputs,
            total_elapsed_ms=total_elapsed_ms,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
        )
        if self._execution_store is not None:
            await self._execution_store.save_execution(
                result, workflow_id, version.version, trigger_payload
            )
        return result

    async def _run_node(self, node: WorkflowNode, inputs: dict[str, Any]) -> _NodeOutput:
        """Execute a single node by delegating to the app context.

        Args:
            node: The workflow node to execute.
            inputs: Resolved inputs for this node.

        Returns:
            A ``_NodeOutput`` wrapping the node's output and any token usage.

        Raises:
            ValueError: If the node type is not supported.
        """
        from hestia.workflows.nodes import NODE_TYPES

        executor_cls = NODE_TYPES.get(node.type)
        if executor_cls is not None:
            executor = executor_cls()
            raw = await executor.execute(self._app, node, inputs)
            if isinstance(raw, ChatResponse):
                return _NodeOutput(
                    value=raw.content,
                    prompt_tokens=raw.prompt_tokens,
                    completion_tokens=raw.completion_tokens,
                )
            return _NodeOutput(value=raw)

        if node.type == "inference":
            prompt = inputs.get("prompt", str(inputs))
            response = await self._app.inference.chat(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )
            return _NodeOutput(
                value=response.content,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
            )

        # Treat node type as a tool name by default
        result = await self._app.tool_registry.call(node.type, inputs)
        return _NodeOutput(value=result.content)
