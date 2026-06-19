"""Session persistence store."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select

from hestia.core.clock import utcnow
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.schema import sessions

logger = logging.getLogger(__name__)

_GET_OR_CREATE_MAX_ATTEMPTS = 5


class SessionStore:
    """Store for session records.

    ``SessionStore`` owns only the ``sessions`` table. Message, turn, and
    handoff operations live in ``MessageStore``, ``TurnStore``, and
    ``HandoffService`` respectively.
    """

    def __init__(
        self,
        db: Database,
        event_bus: Any | None = None,
    ) -> None:
        self._db = db
        self._event_bus = event_bus

    def _emit_session_started(self, session: Session) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish_nowait(
                    "session_started",
                    {
                        "session_id": session.id,
                        "platform": session.platform,
                        "platform_user": session.platform_user,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to publish session_started event")

    async def get_or_create_session(
        self,
        platform: str,
        platform_user: str,
        title: str | None = None,
    ) -> Session:
        """Get the active session for an identity or create one."""
        existing = await self.get_active_session(platform, platform_user)
        if existing is not None:
            return existing

        for attempt in range(_GET_OR_CREATE_MAX_ATTEMPTS):
            try:
                return await self.create_session(
                    platform, platform_user, title=title
                )
            except sa.exc.IntegrityError as exc:
                logger.warning(
                    "get_or_create_session collision (%s, %s) attempt %d/%d: %s",
                    platform,
                    platform_user,
                    attempt + 1,
                    _GET_OR_CREATE_MAX_ATTEMPTS,
                    exc,
                )
                # Another writer won the race; try to read again.
                existing = await self.get_active_session(platform, platform_user)
                if existing is not None:
                    return existing
                if attempt == _GET_OR_CREATE_MAX_ATTEMPTS - 1:
                    raise PersistenceError(
                        f"Could not get_or_create session for {platform}/{platform_user}"
                    ) from exc

        # Unreachable; satisfies the type checker.
        return await self.create_session(platform, platform_user, title=title)

    async def create_session(
        self,
        platform: str,
        platform_user: str,
        title: str | None = None,
        archive_previous: Session | None = None,
    ) -> Session:
        """Create a new session.

        If ``archive_previous`` is provided, it is archived before the new
        session is inserted.
        """
        if archive_previous is not None:
            await self.archive_session(archive_previous.id)

        now = utcnow()
        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            platform=platform,
            platform_user=platform_user,
            state=SessionState.ACTIVE,
            started_at=now,
            last_active_at=now,
            title=title,
            temperature=SessionTemperature.COLD,
            slot_id=None,
            slot_saved_path=None,
        )

        insert = sessions.insert().values(
            id=session.id,
            platform=session.platform,
            platform_user=session.platform_user,
            state=session.state.value,
            started_at=session.started_at,
            last_active_at=session.last_active_at,
            title=session.title,
            temperature=session.temperature.value,
            slot_id=session.slot_id,
            slot_saved_path=session.slot_saved_path,
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

        self._emit_session_started(session)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Fetch a session by id."""
        query = select(sessions).where(sessions.c.id == session_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_session(row)

    async def get_active_session(
        self, platform: str, platform_user: str
    ) -> Session | None:
        """Fetch the active session for an identity, if any."""
        query = (
            select(sessions)
            .where(
                (sessions.c.platform == platform)
                & (sessions.c.platform_user == platform_user)
                & (sessions.c.state == SessionState.ACTIVE.value)
            )
            .order_by(sessions.c.started_at.desc())
            .limit(1)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_session(row)

    async def get_sessions_batch(self, session_ids: list[str]) -> dict[str, Session]:
        """Fetch many sessions by id."""
        if not session_ids:
            return {}
        query = select(sessions).where(sessions.c.id.in_(session_ids))
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return {row.id: self._row_to_session(row) for row in rows}

    async def list_sessions(
        self,
        state: SessionState | None = None,
        platform: str | None = None,
        platform_user: str | None = None,
        limit: int = 100,
    ) -> list[Session]:
        """List sessions with optional filters."""
        query = select(sessions)
        if state is not None:
            query = query.where(sessions.c.state == state.value)
        if platform is not None:
            query = query.where(sessions.c.platform == platform)
        if platform_user is not None:
            query = query.where(sessions.c.platform_user == platform_user)
        query = query.order_by(sessions.c.last_active_at.desc()).limit(limit)

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_session(row) for row in rows]

    async def archive_session(self, session_id: str) -> None:
        """Mark a session as archived."""
        update = (
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(state=SessionState.ARCHIVED.value)
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def end_session(self, session_id: str, reason: str) -> None:
        """Archive a session (reason is logged but not persisted here)."""
        logger.debug("Ending session %s: %s", session_id, reason)
        await self.archive_session(session_id)

    async def assign_slot(
        self,
        session_id: str,
        slot_id: int,
        clear_saved_path: bool = False,
    ) -> None:
        """Assign an inference slot to a session and mark it hot."""
        values: dict[str, Any] = {
            "slot_id": slot_id,
            "temperature": SessionTemperature.HOT.value,
            "last_active_at": utcnow(),
        }
        if clear_saved_path:
            values["slot_saved_path"] = None
        update = sessions.update().where(sessions.c.id == session_id).values(**values)
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def release_slot(
        self,
        session_id: str,
        demote_to: SessionTemperature = SessionTemperature.WARM,
        saved_path: str | None = None,
    ) -> None:
        """Release a session's inference slot and record the new temperature."""
        update = (
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(
                slot_id=None,
                slot_saved_path=saved_path,
                temperature=demote_to.value,
                last_active_at=utcnow(),
            )
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def update_saved_path(
        self, session_id: str, saved_path: str | None
    ) -> None:
        """Update the path where the session's slot state is saved."""
        update = (
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(slot_saved_path=saved_path)
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def update_session_title(self, session_id: str, title: str) -> None:
        """Update a session's title."""
        update = (
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(title=title)
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def count_sessions_by_state(self) -> dict[str, int]:
        """Count sessions grouped by state."""
        query = select(sessions.c.state, sa.func.count(sessions.c.id)).group_by(
            sessions.c.state
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return {row.state: int(row[1]) for row in rows}

    def _row_to_session(self, row: Any) -> Session:
        temperature = SessionTemperature.COLD
        if hasattr(row, "temperature") and row.temperature is not None:
            try:
                temperature = SessionTemperature(row.temperature)
            except ValueError:
                temperature = SessionTemperature.COLD
        return Session(
            id=row.id,
            platform=row.platform,
            platform_user=row.platform_user,
            state=SessionState(row.state),
            started_at=row.started_at,
            last_active_at=row.last_active_at,
            title=row.title if hasattr(row, "title") else None,
            temperature=temperature,
            slot_id=row.slot_id if hasattr(row, "slot_id") else None,
            slot_saved_path=row.slot_saved_path if hasattr(row, "slot_saved_path") else None,
        )
