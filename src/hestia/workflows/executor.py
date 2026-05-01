"""Workflow executor: topological DAG walker with trust enforcement."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from hestia.app import AppContext
from hestia.core.types import Message
from hestia.tools.capabilities import (
    EMAIL_SEND,
    MEMORY_READ,
    MEMORY_WRITE,
    NETWORK_EGRESS,
    SELF_MANAGEMENT,
    SHELL_EXEC,
    WRITE_LOCAL,
)
from hestia.workflows.models import WorkflowEdge, WorkflowNode
from hestia.workflows.store import WorkflowStore

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

    queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
    result: list[WorkflowNode] = []

    while queue:
        n_id = queue.pop(0)
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
class NodeResult:
    """Result of executing a single workflow node."""

    node_id: str
    status: str  # "ok" | "failed"
    output: Any = None
    error: str | None = None


@dataclass
class ExecutionResult:
    """Result of executing a workflow."""

    workflow_id: str
    status: str  # "ok" | "failed"
    node_results: list[NodeResult] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)


class WorkflowExecutor:
    """Executes workflow DAGs with topological ordering and trust enforcement.

    Args:
        app: The application context providing inference, tool registry, and adapters.
    """

    def __init__(self, app: AppContext) -> None:
        self._app = app

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
        store = WorkflowStore(self._app.db)
        workflow = await store.get_workflow(workflow_id)
        if workflow is None:
            return ExecutionResult(
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

        version = await store.get_active_version(workflow_id)
        if version is None:
            return ExecutionResult(
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

        node_results: list[NodeResult] = []
        outputs: dict[str, Any] = {"trigger": trigger_payload}

        try:
            order = _topological_sort(version.nodes, version.edges)
        except ValueError as exc:
            return ExecutionResult(
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

        blocked = _blocked_capabilities(workflow.trust_level)

        for node in order:
            node_caps = set(node.capabilities)
            denied = node_caps & blocked
            if denied:
                result = NodeResult(
                    node_id=node.id,
                    status="failed",
                    error=(
                        f"Trust level '{workflow.trust_level}' denies "
                        f"capabilities: {', '.join(sorted(denied))}"
                    ),
                )
                node_results.append(result)
                return ExecutionResult(
                    workflow_id=workflow_id,
                    status="failed",
                    node_results=node_results,
                    outputs=outputs,
                )

            inputs = _resolve_inputs(node, version.edges, outputs)

            # Seed root nodes (no incoming edges) with the trigger payload
            has_upstream = any(e.target_node_id == node.id for e in version.edges)
            if not has_upstream:
                if isinstance(trigger_payload, dict):
                    inputs = {**trigger_payload, **inputs}
                else:
                    inputs["trigger"] = trigger_payload

            try:
                output = await self._run_node(node, inputs)
            except Exception as exc:
                logger.exception("Node %s failed in workflow %s", node.id, workflow_id)
                result = NodeResult(
                    node_id=node.id,
                    status="failed",
                    error=str(exc),
                )
                node_results.append(result)
                return ExecutionResult(
                    workflow_id=workflow_id,
                    status="failed",
                    node_results=node_results,
                    outputs=outputs,
                )

            result = NodeResult(
                node_id=node.id,
                status="ok",
                output=output,
            )
            node_results.append(result)
            outputs[node.id] = output

        return ExecutionResult(
            workflow_id=workflow_id,
            status="ok",
            node_results=node_results,
            outputs=outputs,
        )

    async def _run_node(self, node: WorkflowNode, inputs: dict[str, Any]) -> Any:
        """Execute a single node by delegating to the app context.

        Args:
            node: The workflow node to execute.
            inputs: Resolved inputs for this node.

        Returns:
            The node's output.

        Raises:
            ValueError: If the node type is not supported.
        """
        if node.type == "inference":
            prompt = inputs.get("prompt", str(inputs))
            response = await self._app.inference.chat(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )
            return response.content

        # Treat node type as a tool name by default
        result = await self._app.tool_registry.call(node.type, inputs)
        return result.content
