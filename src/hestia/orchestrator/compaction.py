"""Manual in-session compaction orchestration for /compact."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hestia.config import CompactionConfig
from hestia.core.clock import utcnow
from hestia.core.types import Message
from hestia.inference.slot_manager import SlotManager
from hestia.memory.compaction_summarizer import (
    CompactionSummary,
    SessionCompactionSummarizer,
)
from hestia.orchestrator.lock import SessionLockManager
from hestia.orchestrator.mappers import message_domain_to_dto, message_dto_to_domain
from hestia.persistence.dto import MessageDTO
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore

logger = logging.getLogger(__name__)


@dataclass
class CompactionOutcome:
    """Outcome of a /compact operation."""

    success: bool
    message: str
    archived_count: int
    summary: CompactionSummary | None = None
    token_cost: int = 0


class SessionCompactor:
    """Orchestrates /compact: summarize, archive, replace, erase slot, flush memory."""

    def __init__(
        self,
        session_store: SessionStore,
        message_store: MessageStore,
        slot_manager: SlotManager,
        summarizer: SessionCompactionSummarizer,
        lock_manager: SessionLockManager,
        config: CompactionConfig,
    ) -> None:
        self._session_store = session_store
        self._message_store = message_store
        self._slot_manager = slot_manager
        self._summarizer = summarizer
        self._lock_manager = lock_manager
        self._config = config

    async def compact(
        self, session_id: str, instruction: str | None = None
    ) -> CompactionOutcome:
        """Compact the session in place.

        Acquires the per-session lock, generates a task-aware summary, archives
        the original messages, replaces active history with the summary plus a
        verbatim tail, erases the KV slot, and flushes structured task-state to
        memory.
        """
        if not self._config.enabled:
            return CompactionOutcome(
                success=False,
                message="Compaction is disabled in configuration.",
                archived_count=0,
            )

        # Refuse if a turn is currently holding the session lock.
        if self._lock_manager.is_locked(session_id):
            return CompactionOutcome(
                success=False,
                message="A turn is currently running for this session; try again after it finishes.",
                archived_count=0,
            )

        session = await self._session_store.get_session(session_id)
        if session is None:
            return CompactionOutcome(
                success=False,
                message="Session not found.",
                archived_count=0,
            )

        lock = await self._lock_manager.acquire(session_id)
        async with lock:
            original_dtos = await self._message_store.get_messages(session_id)
            if len(original_dtos) < self._config.min_messages:
                return CompactionOutcome(
                    success=False,
                    message="Not enough history to compact.",
                    archived_count=0,
                )

            original_messages = [
                message_dto_to_domain(dto) for dto in original_dtos
            ]

            summary_result = await self._summarizer.summarize_and_store(
                session, original_messages, instruction=instruction
            )
            if summary_result is None:
                return CompactionOutcome(
                    success=False,
                    message="Failed to generate a compaction summary.",
                    archived_count=0,
                )

            summary_msg = self._build_summary_message(summary_result.summary)
            tail = self._select_verbatim_tail(original_dtos)
            replacement = [summary_msg, *tail]

            compacted_at = utcnow()
            await self._message_store.archive_and_replace_messages(
                session_id,
                replacement,
                compacted_at,
            )

            # Erase the KV slot so the next turn rebuilds cold from the
            # smaller history. Refresh session first because another writer
            # (e.g., a finalizing turn) may have changed slot state.
            refreshed = await self._session_store.get_session(session_id)
            if refreshed is not None and refreshed.slot_id is not None:
                try:
                    await self._slot_manager.erase(refreshed)
                except Exception:
                    logger.exception(
                        "Slot erase failed after compaction for session %s", session_id
                    )
                    # Non-fatal: the slot is stale and will be rebuilt cold on
                    # the next turn anyway if the DB demotion succeeded.

            archived_count = len(original_dtos)
            logger.info(
                "Compacted session %s: archived %d messages, kept %d verbatim",
                session_id,
                archived_count,
                len(tail),
            )

            return CompactionOutcome(
                success=True,
                message="Session compacted. Original messages archived; KV slot cleared.",
                archived_count=archived_count,
                summary=summary_result.summary,
                token_cost=summary_result.token_cost,
            )

    def _build_summary_message(self, summary: CompactionSummary) -> MessageDTO:
        """Build a synthetic user message from the structured summary."""
        lines = ["[Session compacted — task state]"]
        if summary.goal:
            lines.append(f"Goal: {summary.goal}")
        if summary.criteria:
            lines.append(f"Criteria: {summary.criteria}")
        if summary.progress_done:
            lines.append(f"Done: {summary.progress_done}")
        if summary.pending:
            lines.append(f"Pending: {summary.pending}")
        if summary.key_findings:
            lines.append(f"Key findings: {summary.key_findings}")
        if summary.artifact_paths:
            lines.append(f"Artifacts: {', '.join(summary.artifact_paths)}")
        content = "\n".join(lines)

        return message_domain_to_dto(
            Message(
                role="user",
                content=content,
                is_handoff=True,
            ),
            session_id="",  # filled in by archive_and_replace_messages
            idx=0,
        )

    def _select_verbatim_tail(self, messages: list[MessageDTO]) -> list[MessageDTO]:
        """Return a verbatim tail that preserves the most recent user request.

        Keeps at least ``verbatim_turns * 2`` recent messages, but extends
        backward to include the last user message if the fixed window would
        have cut it off. This prevents a /compact from dropping the user's
        latest directive while the agent is still mid-turn.
        """
        if not messages:
            return []

        keep_count = self._config.verbatim_turns * 2
        if keep_count <= 0:
            return []

        # Find the most recent user message; without it the agent loses the
        # current directive after compaction.
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "user":
                last_user_idx = i
                break

        start = max(0, len(messages) - keep_count)
        if last_user_idx >= 0 and start > last_user_idx:
            start = last_user_idx

        tail = messages[start:]

        # Ensure the tail starts with a user message for clean turn pairing.
        while tail and tail[0].role != "user":
            tail = tail[1:]

        return tail
