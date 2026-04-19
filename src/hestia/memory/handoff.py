"""Session handoff summaries: generate a 2-3 sentence summary on session close."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session
from hestia.memory.store import MemoryStore

logger = logging.getLogger(__name__)

HANDOFF_PROMPT = """You are producing a brief session handoff note.

Summarize the conversation in 2-3 sentences, focused on:
1. What was decided or accomplished.
2. What is still pending.
3. Any facts the operator will want to remember next session.

No pleasantries. No greetings. No bullet lists. Plain prose, <= 350 characters.
"""


@dataclass
class HandoffResult:
    """Result of generating a handoff summary."""

    summary: str
    memory_id: str
    token_cost: int


class SessionHandoffSummarizer:
    """Generates a short summary when a session closes and stores it as memory.

    Example::

        summarizer = SessionHandoffSummarizer(
            inference=inference_client,
            memory_store=memory_store,
            max_chars=350,
            min_messages=4,
        )
        result = await summarizer.summarize_and_store(session, history)
        # result is None for trivial sessions
    """

    def __init__(
        self,
        inference: InferenceClient,
        memory_store: MemoryStore,
        *,
        max_chars: int = 350,
        min_messages: int = 4,
    ) -> None:
        self._inference = inference
        self._memory = memory_store
        self._max_chars = max_chars
        self._min_messages = min_messages

    async def summarize_and_store(
        self,
        session: Session,
        history: list[Message],
    ) -> HandoffResult | None:
        """Generate a handoff summary and persist it. Returns None on skip."""
        # Skip trivial sessions (greetings, single-turn).
        user_msgs = sum(1 for m in history if m.role == "user")
        if user_msgs < self._min_messages:
            return None

        request_msgs: list[Message] = [
            Message(role="system", content=HANDOFF_PROMPT),
            *(m for m in history if m.role in ("user", "assistant") and m.content),
        ]
        response = await self._inference.chat(
            messages=request_msgs,
            tools=[],
            slot_id=None,  # one-shot, no slot state
            reasoning_budget=0,
        )
        summary = (response.content or "").strip()
        if not summary:
            logger.warning("Session handoff produced empty summary for %s", session.id)
            return None
        if len(summary) > self._max_chars:
            summary = summary[: self._max_chars].rstrip() + "…"

        memory = await self._memory.save(
            content=summary,
            tags=["handoff", session.platform],
            session_id=session.id,
        )
        return HandoffResult(
            summary=summary,
            memory_id=memory.id,
            token_cost=(response.prompt_tokens or 0) + (response.completion_tokens or 0),
        )
