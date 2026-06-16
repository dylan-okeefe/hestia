"""Tests for the quality monitor degenerate-pattern detection."""

import pytest

from hestia.core.types import Message, ToolCall
from hestia.orchestrator.quality import _is_read_only_streak

_READ_ONLY_TOOLS = [
    "read_file",
    "list_dir",
    "browser_get",
    "web_search",
    "current_time",
]


def _assistant_with_tool(name: str) -> Message:
    return Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id=f"call_{name}", name=name, arguments={})],
    )


def _user_message(correction: bool = False) -> Message:
    return Message(
        role="user",
        content="keep going" if correction else "real user message",
        correction=correction,
    )


@pytest.mark.parametrize("correction", [True, False])
def test_is_read_only_streak_excludes_corrections(correction: bool) -> None:
    """Injected corrections must not reset a read-only streak.

    A real user message (correction=False) resets the streak; an injected
    correction (correction=True) does not, so the streak should still be
    detected when it crosses the threshold.
    """
    history: list[Message] = []
    # Build a sequence that crosses the threshold only if the injected user
    # message does not reset the count. In reverse order we see: 4 read-only
    # calls, the user message, then 4 more read-only calls.
    for i in range(4):
        history.append(_assistant_with_tool(_READ_ONLY_TOOLS[i % len(_READ_ONLY_TOOLS)]))
    history.append(_user_message(correction=correction))
    for i in range(4, 8):
        history.append(_assistant_with_tool(_READ_ONLY_TOOLS[i % len(_READ_ONLY_TOOLS)]))

    result = _is_read_only_streak(history)

    if correction:
        assert result is True, "correction=True should not reset read-only streak"
    else:
        assert result is False, "correction=False should reset read-only streak"
