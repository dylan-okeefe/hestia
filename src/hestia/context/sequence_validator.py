"""Validator for chat-template compatible message sequences.

Strict chat templates (e.g. Qwen) reject malformed message sequences.  This
module repairs a sequence by dropping messages that violate the template rules
and logging each drop loudly so the issue is visible in logs.
"""

import logging

from hestia.core.types import Message

logger = logging.getLogger(__name__)


def validate_chat_template_sequence(messages: list[Message]) -> list[Message]:
    """Return a repaired copy of ``messages`` that satisfies chat-template rules.

    Rules:

    1. No adjacent ``role="assistant"`` messages.  A dropped assistant message
       does not count as a separator, so any tool result that followed a
       dropped assistant is also dropped unless the previous kept assistant
       owns its ``tool_call_id``.
    2. No orphan ``role="tool"`` messages.  A tool result is kept only when the
       most recently kept assistant message contains a tool call whose
       ``id`` matches the tool message's ``tool_call_id``.

    System, user, and handoff messages are never modified.

    Args:
        messages: Messages assembled by the context builder.

    Returns:
        A new list with invalid messages removed.
    """
    repaired: list[Message] = []
    last_assistant_tool_call_ids: set[str] = set()

    for index, msg in enumerate(messages):
        if msg.role == "assistant":
            if repaired and repaired[-1].role == "assistant":
                logger.warning(
                    "Dropping adjacent assistant message at index %d: %r",
                    index,
                    _snippet(msg.content),
                )
                continue
            repaired.append(msg)
            last_assistant_tool_call_ids = {
                tc.id for tc in (msg.tool_calls or []) if tc.id
            }
        elif msg.role == "tool":
            if (
                last_assistant_tool_call_ids
                and msg.tool_call_id in last_assistant_tool_call_ids
            ):
                repaired.append(msg)
            else:
                logger.warning(
                    "Dropping orphan tool result at index %d (tool_call_id=%r): %r",
                    index,
                    msg.tool_call_id,
                    _snippet(msg.content),
                )
        else:
            # system, user, and any other role pass through untouched.
            repaired.append(msg)

    return repaired


def _snippet(text: str | None, max_len: int = 80) -> str:
    """Return a short, logging-safe snippet of ``text``."""
    if not text:
        return ""
    text = text.replace("\n", " ")
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text
