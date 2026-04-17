"""Tool metadata and decorator."""

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from hestia.tools.types import ToolHandler


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""

    name: str
    public_description: str  # shown to the model in list_tools output
    internal_description: str  # for docs/debugging, never shown to model
    parameters_schema: dict[str, Any]  # JSON Schema
    max_inline_chars: int = 4000  # results above this → artifact + preview
    requires_confirmation: bool = False
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)  # security capabilities
    handler: ToolHandler | None = None


def tool(
    name: str,
    public_description: str,
    internal_description: str = "",
    parameters_schema: dict[str, Any] | None = None,
    max_inline_chars: int = 4000,
    requires_confirmation: bool = False,
    tags: list[str] | None = None,
    capabilities: list[str] | None = None,
) -> Callable[[ToolHandler], ToolHandler]:
    """Decorator to register a tool.

    Attaches ToolMetadata to the function so it can be discovered and registered
    by the ToolRegistry.

    Args:
        name: Tool name (used in call_tool)
        public_description: Description shown to the model
        internal_description: Description for docs/debug (defaults to docstring)
        parameters_schema: JSON Schema for parameters
        max_inline_chars: Results larger than this become artifacts. The inline
                         preview is capped to this same limit.
        requires_confirmation: Whether user confirmation is needed (Phase 1c)
        tags: Tags for filtering tools
        capabilities: Security capability labels (e.g., 'shell_exec', 'write_local')

    Returns:
        Decorator function
    """

    def decorator(func: ToolHandler) -> ToolHandler:
        meta = ToolMetadata(
            name=name,
            public_description=public_description,
            internal_description=internal_description or func.__doc__ or "",
            parameters_schema=parameters_schema or {"type": "object", "properties": {}},
            max_inline_chars=max_inline_chars,
            requires_confirmation=requires_confirmation,
            tags=tags or [],
            capabilities=capabilities or [],
            handler=func,
        )
        func.__hestia_tool__ = meta  # type: ignore[attr-defined]
        return func

    return decorator
