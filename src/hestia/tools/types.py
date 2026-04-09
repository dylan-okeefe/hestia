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


# Type for tool handler functions
ToolHandler = Callable[..., Awaitable[Any]]
