"""Business logic for session handoffs.

Handoff data is stored as messages with ``is_handoff=True`` in the archived
session. No separate ``session_handoffs`` writes happen here.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from hestia.core.clock import utcnow
from hestia.core.types import Message, Session, SessionHandoff, SessionState
from hestia.orchestrator.mappers import message_domain_to_dto, message_dto_to_domain
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore

if __name__ == "__main__":  # pragma: no cover
    pass

logger = logging.getLogger(__name__)

_ARTIFACT_HANDLE_RE = re.compile(r"art_[a-f0-9]{10}")
_HANDOFF_MAX_HISTORY = 8


class HandoffService:
    """Generates, stores, and retrieves handoff summaries between sessions."""

    def __init__(
        self,
        session_store: SessionStore,
        message_store: MessageStore,
    ) -> None:
        self._session_store = session_store
        self._message_store = message_store

    @staticmethod
    def _extract_artifact_handles(messages: list[Message]) -> list[str]:
        """Scan message content for artifact handle references."""
        handles: set[str] = set()
        for msg in messages:
            if msg.content:
                handles.update(_ARTIFACT_HANDLE_RE.findall(msg.content))
        return sorted(handles)

    @staticmethod
    def _format_handoff_message(handoff: SessionHandoff) -> str:
        """Build a synthetic user message from a handoff record."""
        parts: list[str] = ["[Previous session context]"]
        if handoff.summary:
            parts.append(f"Summary: {handoff.summary}")
        if handoff.key_messages:
            parts.append("Recent messages:")
            for msg in handoff.key_messages:
                content = msg.get("content", "")
                if len(content) > 500:
                    content = content[:500].rstrip() + "…"
                parts.append(f"  {msg.get('role', 'unknown')}: {content}")
        if handoff.artifacts:
            parts.append(f"Artifacts: {', '.join(handoff.artifacts)}")
        return "\n".join(parts)

    def _build_handoff_message(
        self, session: Session, messages: list[Message], summary: str | None = None
    ) -> Message:
        """Construct a handoff message for ``session``."""
        key_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ][-_HANDOFF_MAX_HISTORY:]
        artifacts = self._extract_artifact_handles(messages)

        handoff = SessionHandoff(
            previous_session_id=session.id,
            platform=session.platform,
            platform_user=session.platform_user,
            summary=summary or "",
            key_messages=key_messages,
            artifacts=artifacts,
            created_at=utcnow(),
        )
        return Message(
            role="user",
            content=self._format_handoff_message(handoff),
            is_handoff=True,
        )

    async def generate_handoff_summary(
        self, session_id: str, summary: str | None = None
    ) -> None:
        """Archive a session and persist its handoff as a message.

        If ``summary`` is provided, it is used directly. Otherwise the
        archive-time summarizer owned by the session store produces one,
        saves structured facts to long-term memory, and returns the summary
        text for reuse in the handoff message.
        """
        session = await self._session_store.get_session(session_id)
        if session is None:
            logger.warning("generate_handoff_summary called for missing session %s", session_id)
            return

        generated_summary = await self._session_store.archive_session(session_id)

        messages = [
            message_dto_to_domain(dto)
            for dto in await self._message_store.get_messages(session_id)
        ]

        handoff_message = self._build_handoff_message(
            session, messages, summary or generated_summary
        )
        await self._message_store.append_message(
            session_id,
            message_domain_to_dto(handoff_message, session_id, idx=0),
        )

    async def get_recent_handoffs(
        self, platform: str, platform_user: str, limit: int = 1
    ) -> list[dict[str, Any]]:
        """Return recent handoff summaries for a single identity.

        Handoffs are retrieved from archived sessions by looking for
        ``is_handoff=True`` messages.
        """
        archived = await self._session_store.list_sessions(
            state=SessionState.ARCHIVED,
            platform=platform,
            platform_user=platform_user,
            limit=limit * 2,  # fetch a few extra in case some lack handoff messages
        )
        results: list[dict[str, Any]] = []
        for session in archived:
            handoff_messages = await self._message_store.get_handoff_messages(
                session.id, limit=1
            )
            for msg in handoff_messages:
                results.append(
                    {
                        "session_id": session.id,
                        "summary": msg.content,
                        "created_at": msg.created_at.isoformat(),
                    }
                )
            if len(results) >= limit:
                break
        return results[:limit]

    async def list_handoffs_for_identities(
        self, identity_tuples: list[tuple[str, str]], limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return recent handoffs for a list of (platform, platform_user) identities."""
        if not identity_tuples:
            return []

        all_handoffs: list[dict[str, Any]] = []
        for platform, platform_user in identity_tuples:
            handoffs = await self.get_recent_handoffs(platform, platform_user, limit=limit)
            all_handoffs.extend(handoffs)

        all_handoffs.sort(
            key=lambda h: h.get("created_at", ""), reverse=True
        )
        return all_handoffs[:limit]

    async def get_or_create_session_with_handoff(
        self,
        platform: str,
        platform_user: str,
        title: str | None = None,
    ) -> Session:
        """Get or create a session, injecting a handoff if the session is new.

        After ``SessionStore.get_or_create_session`` returns, we check whether
        the session already has messages. If it does not, we look for the most
        recent handoff for this user and prepend a synthetic handoff message so
        the new session retains continuity context.
        """
        session = await self._session_store.get_or_create_session(
            platform, platform_user, title=title
        )
        existing = await self._message_store.get_messages(session.id)
        if not existing:
            handoffs = await self.get_recent_handoffs(
                platform, platform_user, limit=1
            )
            if handoffs:
                handoff = handoffs[0]
                synthetic = Message(
                    role="user",
                    content=handoff["summary"],
                    is_handoff=True,
                )
                await self._message_store.append_message(
                    session.id,
                    message_domain_to_dto(synthetic, session.id, idx=0),
                )
        return session
