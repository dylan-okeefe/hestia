"""Session summary generation for long-term memory persistence."""

from __future__ import annotations

import logging

from hestia.core.inference import InferenceClient
from hestia.core.types import Message

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """You are summarizing a conversation for long-term memory storage.

Summarize the key points, facts, preferences, and outcomes from this conversation.
Be concise but comprehensive. Focus on information that would be useful to remember
in future sessions.
"""


class SessionSummarizer:
    """Generates a text summary of session messages using the inference client."""

    def __init__(self, inference: InferenceClient) -> None:
        self._inference = inference

    async def summarize(self, messages: list[Message]) -> str:
        """Generate a text summary of a session's messages.

        Filters to user/assistant roles with actual content.
        Returns empty string for insufficient dialogue.

        Args:
            messages: Session message history.

        Returns:
            Summary text, or empty string if there is insufficient dialogue
            or summarization fails.
        """
        dialogue = [m for m in messages if m.role in ("user", "assistant") and m.content]
        if len(dialogue) < 2:
            return ""

        request_msgs = [
            Message(role="system", content=_SUMMARY_PROMPT),
            *dialogue,
        ]

        try:
            response = await self._inference.chat(
                messages=request_msgs,
                tools=[],
                slot_id=None,
                reasoning_budget=0,
            )
        except Exception:
            logger.exception("Session summarization failed")
            return ""

        summary = (response.content or "").strip()
        return summary
