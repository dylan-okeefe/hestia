"""Classify tool-result content into high-level failure categories."""

from enum import Enum, auto


class ToolResultCategory(Enum):
    """High-level outcome of a tool call."""

    SUCCESS = auto()
    TIMEOUT = auto()
    BLOCKED = auto()
    NOT_FOUND = auto()
    TRANSIENT_OTHER = auto()


def classify_tool_result(content: str, tool_name: str = "") -> ToolResultCategory:
    """Classify a tool-result string.

    Rules are case-insensitive substring matches, ordered from most-specific
    permanent failures to generic transient errors. ``SUCCESS`` is the default
    when no failure marker is present.
    """
    lowered = (content or "").lower()

    if any(marker in lowered for marker in ("timeout", "timed out")):
        return ToolResultCategory.TIMEOUT

    if any(
        marker in lowered
        for marker in (
            "404",
            "not found",
            "page doesn't exist",
            "page is gone",
            "url returns 404",
        )
    ):
        return ToolResultCategory.NOT_FOUND

    if any(
        marker in lowered
        for marker in (
            "403",
            "blocked",
            "bot protection",
            "cloudflare",
            "captcha",
            "humans only",
            "login",
            "sign in",
            "unauthorized",
            "access denied",
        )
    ):
        return ToolResultCategory.BLOCKED

    if any(
        marker in lowered for marker in ("error", "failed", "partial failure")
    ):
        return ToolResultCategory.TRANSIENT_OTHER

    return ToolResultCategory.SUCCESS
