"""Message persistence store."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select

from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.dto import MessageDTO
from hestia.persistence.schema import compaction_archive, messages, sessions

logger = logging.getLogger(__name__)

# Retry constants copied from the original sessions.py implementation.
_APPEND_IDX_MAX_ATTEMPTS = 10


class MessageStore:
    """Store for chat messages.

    ``MessageStore`` owns the ``messages`` table. The one cross-table
    operation it keeps is ``append_message``: it inserts the message row
    and bumps ``sessions.last_active_at`` in a single connection/commit.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def append_message(self, session_id: str, msg: MessageDTO) -> None:
        """Append a message to a session and update last_active_at.

        This method is intentionally self-contained and atomic: the message
        insert and the session touch share one connection and commit.
        """
        for attempt in range(_APPEND_IDX_MAX_ATTEMPTS):
            try:
                async with self._db.engine.connect() as conn:
                    idx_query = select(sa.func.coalesce(sa.func.max(messages.c.idx), -1) + 1).where(
                        messages.c.session_id == session_id
                    )
                    result = await conn.execute(idx_query)
                    idx = result.scalar_one()

                    insert = messages.insert().values(
                        session_id=session_id,
                        idx=idx,
                        role=msg.role,
                        content=msg.content,
                        tool_calls=msg.tool_calls,
                        tool_call_id=msg.tool_call_id,
                        reasoning_content=msg.reasoning_content,
                        is_handoff=msg.is_handoff,
                        correction=msg.correction,
                        created_at=msg.created_at,
                    )
                    await conn.execute(insert)

                    await conn.execute(
                        sessions.update()
                        .where(sessions.c.id == session_id)
                        .values(last_active_at=utcnow())
                    )

                    await conn.commit()
                    return
            except sa.exc.IntegrityError:
                logger.debug(
                    "Message idx collision for session %s, attempt %d/%d",
                    session_id,
                    attempt + 1,
                    _APPEND_IDX_MAX_ATTEMPTS,
                )
                if attempt == _APPEND_IDX_MAX_ATTEMPTS - 1:
                    raise PersistenceError(
                        f"Failed to append message after {_APPEND_IDX_MAX_ATTEMPTS} attempts"
                    ) from None
                continue

    async def get_messages(self, session_id: str) -> list[MessageDTO]:
        """Return all messages for a session in order."""
        query = (
            select(messages)
            .where(messages.c.session_id == session_id)
            .order_by(messages.c.idx)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_message(row) for row in rows]

    async def archive_and_replace_messages(
        self,
        session_id: str,
        replacement_messages: list[MessageDTO],
        compacted_at: datetime,
    ) -> None:
        """Archive every existing message and replace them with a new sequence.

        The original messages are copied to ``compaction_archive`` with their
        original indexes, then deleted from ``messages``. The replacement
        messages are inserted with fresh contiguous indexes starting at 0.
        This is atomic within a single transaction.
        """
        async with self._db.engine.begin() as conn:
            # 1. Copy originals to archive.
            original_rows = await conn.execute(
                select(messages).where(messages.c.session_id == session_id).order_by(messages.c.idx)
            )
            archive_values: list[dict[str, Any]] = []
            for row in original_rows.fetchall():
                archive_values.append(
                    {
                        "session_id": row.session_id,
                        "original_idx": row.idx,
                        "role": row.role,
                        "content": row.content,
                        "tool_calls": row.tool_calls,
                        "tool_call_id": row.tool_call_id,
                        "reasoning_content": row.reasoning_content,
                        "is_handoff": bool(row.is_handoff),
                        "correction": bool(row.correction),
                        "created_at": row.created_at,
                        "compacted_at": compacted_at,
                    }
                )
            if archive_values:
                await conn.execute(compaction_archive.insert(), archive_values)

            # 2. Delete originals.
            await conn.execute(messages.delete().where(messages.c.session_id == session_id))

            # 3. Insert replacements with fresh indexes.
            for idx, msg in enumerate(replacement_messages):
                await conn.execute(
                    messages.insert().values(
                        session_id=session_id,
                        idx=idx,
                        role=msg.role,
                        content=msg.content,
                        tool_calls=msg.tool_calls,
                        tool_call_id=msg.tool_call_id,
                        reasoning_content=msg.reasoning_content,
                        is_handoff=msg.is_handoff,
                        correction=msg.correction,
                        created_at=msg.created_at,
                    )
                )

            # 4. Touch session last_active_at.
            await conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(last_active_at=utcnow())
            )

    async def get_handoff_messages(self, session_id: str, limit: int = 1) -> list[MessageDTO]:
        """Return handoff messages for a session, newest first."""
        query = (
            select(messages)
            .where(
                (messages.c.session_id == session_id) & (messages.c.is_handoff.is_(True))
            )
            .order_by(messages.c.idx.desc())
            .limit(limit)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_message(row) for row in rows]

    async def has_messages(self, session_id: str) -> bool:
        """Return True if the session has any messages."""
        query = select(sa.func.count(messages.c.idx)).where(
            messages.c.session_id == session_id
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            return bool(result.scalar_one())

    def _row_to_message(self, row: Any) -> MessageDTO:
        return MessageDTO(
            session_id=row.session_id,
            idx=row.idx,
            role=row.role,
            content=row.content,
            created_at=row.created_at,
            tool_calls=row.tool_calls,
            tool_call_id=row.tool_call_id,
            reasoning_content=row.reasoning_content,
            is_handoff=bool(row.is_handoff),
            correction=bool(row.correction),
        )
