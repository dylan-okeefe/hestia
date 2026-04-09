"""Tool registry with meta-tool dispatch."""

import json
from types import ModuleType
from typing import Any

from hestia.artifacts.store import ArtifactStore
from hestia.core.types import FunctionSchema, ToolSchema
from hestia.errors import HestiaError
from hestia.tools.metadata import ToolMetadata, tool
from hestia.tools.types import ToolCallResult


class ToolError(HestiaError):
    """Tool-related error."""

    pass


class ToolNotFoundError(ToolError):
    """Tool not found in registry."""

    pass


class ToolRegistry:
    """Registry for tools with meta-tool dispatch.

    The meta-tool pattern reduces tool overhead from ~3000 tokens (listing all tool
    schemas) to ~80 tokens (just list_tools and call_tool schemas).
    """

    def __init__(self, artifact_store: ArtifactStore):
        """Initialize with an artifact store for large results."""
        self._tools: dict[str, ToolMetadata] = {}
        self._artifact_store = artifact_store

    def register(self, func: Any) -> None:
        """Register a function decorated with @tool.

        Args:
            func: Function with __hestia_tool__ metadata attached

        Raises:
            ValueError: If func is not decorated with @tool
            ValueError: If tool name is already registered
        """
        meta = getattr(func, "__hestia_tool__", None)
        if meta is None:
            raise ValueError(f"{func} is not decorated with @tool")
        if meta.name in self._tools:
            raise ValueError(f"Tool {meta.name!r} already registered")
        self._tools[meta.name] = meta

    def register_module(self, module: ModuleType) -> None:
        """Scan a module and register all @tool-decorated functions."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and hasattr(attr, "__hestia_tool__"):
                self.register(attr)

    def list_names(self, tag: str | None = None) -> list[str]:
        """List registered tool names.

        Args:
            tag: Optional tag filter

        Returns:
            Sorted list of tool names
        """
        if tag is None:
            return sorted(self._tools.keys())
        return sorted(n for n, m in self._tools.items() if tag in m.tags)

    def describe(self, name: str) -> ToolMetadata:
        """Get metadata for a tool.

        Args:
            name: Tool name

        Returns:
            ToolMetadata

        Raises:
            ToolNotFoundError: If tool doesn't exist
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool not found: {name}")
        return self._tools[name]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """Dispatch a tool call.

        Handles truncation and auto-promotion to artifacts for large results.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            ToolCallResult with status, content, and optional artifact handle
        """
        meta = self.describe(name)
        if meta.handler is None:
            raise ToolError(f"Tool {name!r} has no handler")

        try:
            raw = await meta.handler(**arguments)
        except Exception as e:
            return ToolCallResult(
                status="error",
                content=f"{type(e).__name__}: {e}",
                artifact_handle=None,
                truncated=False,
            )

        # Normalize to string
        content_str = (
            json.dumps(raw, indent=2) if isinstance(raw, (dict, list)) else str(raw)
        )

        return self._postprocess(content_str, meta)

    def _postprocess(self, content: str, meta: ToolMetadata) -> ToolCallResult:
        """Post-process tool result: truncate and/or promote to artifact."""
        size = len(content)

        if size >= meta.auto_artifact_above:
            # Store full content as artifact, return a preview + handle
            handle = self._artifact_store.store(
                content.encode("utf-8"),
                content_type="text/plain",
                source_tool=meta.name,
            )
            preview = content[: meta.max_result_chars]
            return ToolCallResult(
                status="ok",
                content=(
                    f"[full result stored as artifact {handle}; "
                    f"showing first {len(preview)} of {size} chars]\n\n{preview}"
                ),
                artifact_handle=handle,
                truncated=size > meta.max_result_chars,
            )

        return ToolCallResult(
            status="ok",
            content=content,
            artifact_handle=None,
            truncated=False,
        )

    # --- Meta-tool schemas (what the model actually sees) ---

    def meta_tool_schemas(self) -> list[ToolSchema]:
        """Return the two meta-tools (list_tools, call_tool) as ToolSchema."""
        list_tools_schema = ToolSchema(
            type="function",
            function=FunctionSchema(
                name="list_tools",
                description=(
                    "List all available tools. Returns tool names and one-line descriptions. "
                    "Call this before call_tool to discover what's available."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "description": "Optional tag filter",
                        }
                    },
                },
            ),
        )

        call_tool_schema = ToolSchema(
            type="function",
            function=FunctionSchema(
                name="call_tool",
                description=(
                    "Invoke a tool by name with arguments. Use list_tools first to "
                    "discover what exists."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the tool to call",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Arguments for the tool",
                        },
                    },
                    "required": ["name", "arguments"],
                },
            ),
        )

        return [list_tools_schema, call_tool_schema]

    async def meta_list_tools(self, tag: str | None = None) -> str:
        """Handler for the list_tools meta-tool."""
        names = self.list_names(tag=tag)
        lines = []
        for n in names:
            m = self._tools[n]
            lines.append(f"- {n}: {m.public_description}")
        return "\n".join(lines) if lines else "(no tools)"

    async def meta_call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """Handler for the call_tool meta-tool."""
        return await self.call(name, arguments)


# Re-export for convenience
__all__ = ["ToolRegistry", "ToolMetadata", "tool", "ToolError", "ToolNotFoundError"]
