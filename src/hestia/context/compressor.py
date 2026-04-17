"""History compression for context overflow recovery."""

from __future__ import annotations

import logging
from typing import Protocol

from hestia.core.inference import InferenceClient
from hestia.core.types import Message

logger = logging.getLogger(__name__)


class HistoryCompressor(Protocol):
    """Protocol for compressing dropped conversation history.

    Implementations receive the list of messages that were dropped from
    context due to budget pressure and return a short prose summary.
    """

    async def summarize(self, dropped: list[Message]) -> str:
        """Summarize dropped messages.

        Args:
            dropped: Messages that were removed from context, in chronological order.

        Returns:
            A short prose summary (<= 400 chars by convention). Empty string
            if compression fails or should be skipped.
        """
        ...


class InferenceHistoryCompressor:
    """Default compressor that calls the same InferenceClient with a short prompt.

    Example::

        compressor = InferenceHistoryCompressor(inference_client, max_chars=400)
        summary = await compressor.summarize(dropped_messages)
    """

    PROMPT = (
        "You are compressing older conversation history so the model can continue.\n"
        "Summarize the following exchanges in <= 400 characters, preserving:\n"
        "- User intent and any decisions made\n"
        "- Facts the assistant learned about the user\n"
        "- Open questions or pending actions\n"
        "Do not address the user. Output a single prose paragraph."
    )

    def __init__(self, inference: InferenceClient, *, max_chars: int = 400) -> None:
        self._inference = inference
        self._max_chars = max_chars

    async def summarize(self, dropped: list[Message]) -> str:
        """Compress dropped messages into a short summary."""
        if not dropped:
            return ""
        request = [
            Message(role="system", content=self.PROMPT),
            *(m for m in dropped if m.role in ("user", "assistant") and m.content),
        ]
        try:
            response = await self._inference.chat(
                messages=request, tools=[], slot_id=None, reasoning_budget=0
            )
        except Exception:  # noqa: BLE001 — compressor is best-effort
            logger.warning("History compressor failed; falling back to truncation", exc_info=True)
            return ""
        summary = (response.content or "").strip()
        return summary[: self._max_chars].rstrip()
