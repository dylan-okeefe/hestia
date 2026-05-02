"""Tool call node: invokes a registered tool by name."""

from __future__ import annotations

from typing import Any

from hestia.app import AppContext
from hestia.workflows.models import WorkflowNode


class ToolCallNode:
    """Executes a registered tool by name."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
    ) -> Any:
        """Call the tool specified in ``node.config['tool_name']``.

        Args:
            app: Application context.
            node: The workflow node.
            inputs: Resolved inputs for this node.

        Returns:
            The tool call result content.

        Raises:
            ValueError: If ``tool_name`` is not specified.
        """
        tool_name = node.config.get("tool_name")
        if not tool_name:
            raise ValueError("ToolCallNode requires 'tool_name' in config")

        result = await app.tool_registry.call(tool_name, inputs)
        return result.content
