"""Tool-related types."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallResult:
    """Result of executing a tool.

    ``error_type`` is the name of the originating exception class when
    ``status == "error"``. It is populated by
    :meth:`hestia.tools.registry.ToolRegistry.call` so the orchestrator
    can branch on the failure class (``"TypeError"``, ``"HTTPError"``,
    ``"ToolExecutionError"`` …) without string-matching the message.
    """

    status: str  # "ok" | "error"
    content: str
    artifact_handle: str | None
    truncated: bool
    error_type: str | None = None

    @classmethod
    def error(cls, content: str, error_type: str | None = None) -> "ToolCallResult":
        return cls(
            status="error",
            content=content,
            artifact_handle=None,
            truncated=False,
            error_type=error_type,
        )


# Type for tool handler functions
ToolHandler = Callable[..., Awaitable[Any]]
