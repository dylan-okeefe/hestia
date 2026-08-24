"""Tool call node: invokes a registered tool by name."""

from __future__ import annotations

import asyncio
from typing import Any

from hestia.app import AppContext
from hestia.workflows.interpolation import interpolate
from hestia.workflows.models import WorkflowNode
from hestia.workflows.tool_selection import resolve_invoked_tools


class ToolCallNode:
    """Executes a registered tool by name."""

    async def execute(
        self,
        app: AppContext,
        node: WorkflowNode,
        inputs: dict[str, Any],
        tool_context: Any = None,
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
        # Shared resolver keeps the gate and the node in agreement (SEC-001).
        resolved_names = resolve_invoked_tools("tool_call", node, inputs)
        tool_name = resolved_names[0]

        # Interpolate {{...}} templates in string inputs so that config
        # values like "{{data.from_address}}" resolve to actual values.
        resolved = {
            k: interpolate(v, inputs) if isinstance(v, str) else v
            for k, v in inputs.items()
        }

        # Filter inputs to only include keys the tool accepts
        try:
            meta = app.tool_registry.describe(tool_name)
            allowed = set(meta.parameters_schema.get("properties", {}).keys())
            tool_inputs = {k: v for k, v in resolved.items() if k in allowed}
        except Exception:
            # If describe fails or schema is unavailable, strip known meta keys
            tool_inputs = {k: v for k, v in resolved.items() if k != "tool_name"}

        result = await app.tool_registry.call(tool_name, tool_inputs, context=tool_context)
        if result.artifact_handle:
            # PERF-017: keep blocking disk I/O off the event loop.
            full_bytes = await asyncio.to_thread(
                app.artifact_store.fetch_content, result.artifact_handle
            )
            return full_bytes.decode("utf-8", errors="replace")
        return result.content
