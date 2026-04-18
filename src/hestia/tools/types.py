"""Tool-related types."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallResult:
    """Result of executing a tool."""

    status: str  # "ok" | "error"
    content: str
    artifact_handle: str | None
    truncated: bool

    @classmethod
    def error(cls, content: str) -> "ToolCallResult":
        return cls(status="error", content=content, artifact_handle=None, truncated=False)


# Type for tool handler functions
ToolHandler = Callable[..., Awaitable[Any]]
