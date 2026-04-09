"""Tool-related types."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class ToolCallResult:
    """Result of executing a tool."""

    status: str  # "ok" | "error"
    content: str
    artifact_handle: str | None
    truncated: bool


# Type for tool handler functions
ToolHandler = Callable[..., Awaitable[Any]]
