"""Built-in workflow node types."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from hestia.app import AppContext
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.condition import ConditionNode
from hestia.workflows.nodes.http_request import HttpRequestNode
from hestia.workflows.nodes.llm_decision import LLMDecisionNode
from hestia.workflows.nodes.send_message import SendMessageNode
from hestia.workflows.nodes.tool_call import ToolCallNode


@runtime_checkable
class NodeExecutor(Protocol):
    """Protocol for workflow node executors."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Execute the node.

        Args:
            app: The application context.
            node: The workflow node definition.
            inputs: Resolved inputs for this node.

        Returns:
            The node output.
        """


NODE_TYPES: dict[str, type[NodeExecutor]] = {
    "tool_call": ToolCallNode,
    "llm_decision": LLMDecisionNode,
    "send_message": SendMessageNode,
    "http_request": HttpRequestNode,
    "condition": ConditionNode,
}


__all__ = [
    "NodeExecutor",
    "NODE_TYPES",
    "ToolCallNode",
    "LLMDecisionNode",
    "SendMessageNode",
    "HttpRequestNode",
    "ConditionNode",
]
