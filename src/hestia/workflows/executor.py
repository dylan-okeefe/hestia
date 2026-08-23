"""Workflow executor: topological DAG walker with trust enforcement."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hestia.app import AppContext
from hestia.core.types import ChatResponse, Message
from hestia.policy.channel import Channel
from hestia.policy.gate import CapabilityRequest
from hestia.policy.identity import Identity
from hestia.workflows.models import ExecutionResult, NodeResult, Workflow, WorkflowEdge, WorkflowNode
from hestia.workflows.store import WorkflowStore

if TYPE_CHECKING:
    from hestia.workflows.execution_store import ExecutionStore

logger = logging.getLogger(__name__)

# SEC-001: node types that invoke tools by name must pass the CapabilityGate
# before dispatch. The old NODE_TYPES-dispatch-then-return flow skipped the
# gate block entirely, letting any activated workflow run arbitrary tools
# (including 'terminal') unattended.
_GATED_NODE_TYPES = {"tool_call", "investigate"}


def _clean_reasoning_fallback(text: str) -> str:
    """Strip markdown formatting from a reasoning model's final line."""
    text = re.sub(r"^[\s*\-+•]+", "", text)
    text = text.replace("`", "")
    text = re.sub(r"\*\*?(.*?)\*\*?", r"\1", text)
    text = text.strip('"\'')
    return text.strip()


def _extract_url_from_text(text: str) -> str | None:
    """Extract the first URL found in text."""
    match = re.search(r"https?://[^\s<>\"\')\]]+", text)
    return match.group(0) if match else None


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
    source_node_id. Node config is merged on top as defaults. The original
    trigger payload is always available under ``inputs["data"]``.
    """
    inputs: dict[str, Any] = dict(node.config)
    trigger_payload = outputs.get("trigger")
    if trigger_payload is not None:
        inputs["data"] = trigger_payload
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
        *,
        is_test: bool = False,
    ) -> None:
        self._app = app
        self._workflow_store = workflow_store
        self._execution_store = execution_store
        self._is_test = is_test

    async def execute(
        self,
        workflow_id: str,
        trigger_payload: Any,
        version_id: str | None = None,
    ) -> ExecutionResult:
        """Execute a workflow by its ID.

        Loads the workflow and its active version (or a specific version if
        version_id is provided), topologically sorts the nodes, and executes
        them in dependency order with trust checks and fail-fast semantics.

        Args:
            workflow_id: The unique identifier of the workflow.
            trigger_payload: The payload that triggered the workflow execution.
            version_id: Optional ``{workflow_id}:{version}`` string to execute
                a specific version instead of the active one.

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

        if version_id is not None:
            if ":" in version_id:
                _, version_str = version_id.rsplit(":", 1)
            else:
                version_str = version_id
            try:
                version_num = int(version_str)
            except ValueError:
                result = ExecutionResult(
                    workflow_id=workflow_id,
                    status="failed",
                    node_results=[
                        NodeResult(
                            node_id="",
                            status="failed",
                            error=f"Invalid version ID: {version_id}",
                        )
                    ],
                )
                if self._execution_store is not None:
                    await self._execution_store.save_execution(
                        result, workflow_id, 0, trigger_payload
                    )
                return result
            version = await store.get_version(workflow_id, version_num)
            if version is None:
                result = ExecutionResult(
                    workflow_id=workflow_id,
                    status="failed",
                    node_results=[
                        NodeResult(
                            node_id="",
                            status="failed",
                            error=f"Version not found: {version_id}",
                        )
                    ],
                )
                if self._execution_store is not None:
                    await self._execution_store.save_execution(
                        result, workflow_id, 0, trigger_payload
                    )
                return result
        else:
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

        # BUG-036: persist a RUNNING row upfront so a crash mid-run leaves an
        # observable trace instead of silently vanishing.
        running_execution_id: str | None = None
        if self._execution_store is not None:
            try:
                running_execution_id = await self._execution_store.start_execution(
                    workflow_id,
                    version.version,
                    trigger_payload,
                    is_test=self._is_test,
                )
            except Exception:
                logger.exception("Failed to record RUNNING execution row")

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

        active_edges: set[str] = set()

        for node in order:
            incoming = [e for e in version.edges if e.target_node_id == node.id]
            if incoming and not any(e.id in active_edges for e in incoming):
                # BUG-039: record skipped nodes so the UI can distinguish
                # 'branch not taken' from 'node does not exist'.
                node_results.append(NodeResult(node_id=node.id, status="skipped"))
                continue

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
                node_output = await self._run_node(node, inputs, workflow)
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
                        result,
                        workflow_id,
                        version.version,
                        trigger_payload,
                        execution_id=running_execution_id,
                        is_test=self._is_test,
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

            outgoing_edges = [e for e in version.edges if e.source_node_id == node.id]
            single_edge = len(outgoing_edges) == 1
            for edge in outgoing_edges:
                if node.type == "condition":
                    expected = "true" if node_output.value else "false"
                    if (single_edge and edge.source_handle is None) or edge.source_handle == expected:
                        active_edges.add(edge.id)
                elif node.type == "llm_decision":
                    if (single_edge and edge.source_handle is None) or edge.source_handle == str(node_output.value):
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
                result,
                workflow_id,
                version.version,
                trigger_payload,
                execution_id=running_execution_id,
                is_test=self._is_test,
            )
        if self._app.event_bus is not None:
            await self._app.event_bus.publish(
                "workflow_completed",
                {
                    "workflow_id": workflow_id,
                    "source_workflow_id": workflow_id,
                    "status": result.status,
                    "platform": "workflow",
                },
            )
        return result

    async def _gate_node_tools(
        self,
        node: WorkflowNode,
        inputs: dict[str, Any],
        workflow: Workflow,
    ) -> None:
        """Run every tool a tool_call/investigate node will invoke past the
        CapabilityGate (SEC-001). Mirrors the fallback-path denial format so
        blocked executions read consistently."""
        gate = self._app.capability_gate
        if gate is None:
            return

        actor = Identity(
            platform="workflow",
            platform_user=workflow.owner_id or workflow.id,
        )
        names: list[str] = []
        if node.type == "tool_call":
            name = node.config.get("tool_name")
            if isinstance(name, str) and name:
                names.append(name)
        elif node.type == "investigate":
            # Mirror InvestigateNode._resolve precedence: inputs over config.
            raw = inputs.get("tools", node.config.get("tools"))
            if isinstance(raw, str):
                names.extend(t.strip() for t in raw.split(",") if t.strip())
            elif isinstance(raw, list):
                names.extend(str(t) for t in raw)

        allow_list = set(workflow.allow_listed_tools or [])
        for tool_name in names:
            request = CapabilityRequest(
                actor=actor,
                channel=Channel.WORKFLOW,
                tool_name=tool_name,
                inputs=dict(inputs),
                source_workflow_id=workflow.id,
            )
            result = await gate.check(request, allow_list=allow_list)
            if not result.allowed:
                raise ValueError(
                    f"[CATEGORY: BLOCKED] Capability gate denied '{tool_name}' "
                    f"in workflow {workflow.id}: {result.reason}"
                )

    async def _run_node(
        self, node: WorkflowNode, inputs: dict[str, Any], workflow: Workflow
    ) -> _NodeOutput:
        """Execute a single node by delegating to the app context.

        Args:
            node: The workflow node to execute.
            inputs: Resolved inputs for this node.
            workflow: The workflow this node belongs to.

        Returns:
            A ``_NodeOutput`` wrapping the node's output and any token usage.

        Raises:
            ValueError: If the node type is not supported.
        """
        from hestia.workflows.nodes import NODE_TYPES

        if node.type in _GATED_NODE_TYPES:
            await self._gate_node_tools(node, inputs, workflow)

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
                max_tokens=4096,
                reasoning_budget=512,
            )
            content = response.content or ""
            if not content and response.reasoning_content:
                # Fallback: some reasoning models (e.g. Qwen3.5-DeepSeek)
                # put their answer in reasoning_content when the prompt is
                # long. Extract the last non-empty line as the answer.
                lines = [
                    line.strip()
                    for line in response.reasoning_content.strip().split("\n")
                    if line.strip()
                ]
                if lines:
                    content = _clean_reasoning_fallback(lines[-1])
                    # If the cleaned line looks like it contains a URL,
                    # try to extract just the URL.
                    url = _extract_url_from_text(content)
                    if url:
                        content = url

            return _NodeOutput(
                value=content,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
            )

        # Treat node type as a tool name by default
        if self._app.capability_gate is not None:
            actor = Identity(
                platform="workflow",
                platform_user=workflow.owner_id or workflow.id,
            )
            request = CapabilityRequest(
                actor=actor,
                channel=Channel.WORKFLOW,
                tool_name=node.type,
                inputs=inputs,
                session_id=None,
            )
            gate_result = await self._app.capability_gate.check(
                request, allow_list=workflow.allow_listed_tools
            )
            if not gate_result.allowed:
                raise ValueError(
                    f"[CATEGORY: BLOCKED] Capability gate denied '{node.type}' "
                    f"in workflow {workflow.id}: {gate_result.reason}"
                )

        result = await self._app.tool_registry.call(node.type, inputs)
        value = result.content
        if result.artifact_handle:
            # Load full artifact content so downstream nodes get the complete
            # data. Off-loop: large reads previously stalled the whole event
            # loop (PERF-017).
            full_bytes = await asyncio.to_thread(
                self._app.artifact_store.fetch_content, result.artifact_handle
            )
            value = full_bytes.decode("utf-8", errors="replace")
        return _NodeOutput(value=value)
