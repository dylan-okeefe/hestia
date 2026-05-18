"""Session persistence layer."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from hestia.core.clock import utcnow
from hestia.core.types import (
    Message,
    Session,
    SessionHandoff,
    SessionState,
    SessionTemperature,
    ToolCall,
)
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.schema import messages, sessions

if TYPE_CHECKING:
    from hestia.events.bus import EventBus
    from hestia.orchestrator.types import Turn, TurnTransition

logger = logging.getLogger(__name__)

# Maximum retry attempts for idx-collision races on append_message /
# append_transition. With n concurrent writers the probability of
# surviving n retries is > 99.99% for n=5.
_APPEND_IDX_MAX_ATTEMPTS = 5

# Regex for artifact handles embedded in message content (art_ + 10 hex chars).
_ARTIFACT_HANDLE_RE = re.compile(r"art_[a-f0-9]{10}")


def _generate_session_id(platform: str, platform_user: str) -> str:
    """Generate a sortable, debuggable session ID."""
    timestamp = utcnow().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{platform}_{platform_user}_{timestamp}_{short_uuid}"


class SessionStore:
    """Typed CRUD wrapper for session persistence."""

    def __init__(self, db: Database, event_bus: EventBus | None = None) -> None:
        """Initialize with a Database instance."""
        self._db = db
        self._event_bus = event_bus

    async def get_or_create_session(self, platform: str, platform_user: str) -> Session:
        """Get the user's active session, or create one atomically.

        TOCTOU-safe: the prior implementation issued a SELECT-then-INSERT pair
        with no isolation between them, so two concurrent callers for the same
        ``(platform, platform_user)`` could both observe "no active session"
        and both create one — yielding duplicate ACTIVE rows that downstream
        code (orchestrator, slot manager, scheduler) treats as a single
        coherent conversation. Symptoms include split message history,
        scheduler tasks attached to a session that never receives messages,
        and slot churn.

        The fix is twofold:

        1. A partial unique index ``ux_sessions_active_user`` on
           ``(platform, platform_user) WHERE state = 'ACTIVE'`` (defined in
           ``schema.py`` and applied via the runtime migration) makes
           duplicate ACTIVE rows a constraint violation at the database layer.
        2. This method now issues a single ``INSERT ... ON CONFLICT DO NOTHING``
           and, on conflict, falls through to a SELECT of the existing winner
           and bumps its ``last_active_at``. Net behavior is identical for
           callers; concurrent callers converge on the same ``Session.id``.

        Dialect handling: SQLite and PostgreSQL both have
        ``INSERT ... ON CONFLICT`` but it lives in dialect-specific modules.
        We dispatch on ``conn.dialect.name`` rather than maintaining two code
        paths at the call sites.
        """
        new_session = Session(
            id=_generate_session_id(platform, platform_user),
            platform=platform,
            platform_user=platform_user,
            started_at=utcnow(),
            last_active_at=utcnow(),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )
        values = {
            "id": new_session.id,
            "platform": new_session.platform,
            "platform_user": new_session.platform_user,
            "started_at": new_session.started_at,
            "last_active_at": new_session.last_active_at,
            "slot_id": new_session.slot_id,
            "slot_saved_path": new_session.slot_saved_path,
            "state": new_session.state.value,
            "temperature": new_session.temperature.value,
        }

        async with self._db.engine.connect() as conn:
            insert_stmt = self._build_active_session_upsert(conn.dialect.name, values)
            insert_result = await conn.execute(insert_stmt)
            inserted_row = insert_result.fetchone()

            if inserted_row is not None:
                # We won the race (or there was no race): the row we just
                # inserted IS the active session. Commit and return it.
                await conn.commit()
                if self._event_bus is not None:
                    await self._event_bus.publish(
                        "session_started",
                        {
                            "session_id": new_session.id,
                            "platform": platform,
                            "platform_user": platform_user,
                        },
                    )
                return new_session

            # ON CONFLICT DO NOTHING swallowed the insert — another concurrent
            # caller already created the active session for this user. Read it,
            # bump last_active_at to match the prior code path's behavior on a
            # cache hit, and return.
            select_stmt = (
                sa.select(sessions)
                .where(
                    sa.and_(
                        sessions.c.platform == platform,
                        sessions.c.platform_user == platform_user,
                        sessions.c.state == SessionState.ACTIVE.value,
                    )
                )
                .order_by(sessions.c.last_active_at.desc())
                .limit(1)
            )
            select_result = await conn.execute(select_stmt)
            row = select_result.fetchone()
            if row is None:
                # Should be impossible: the unique index just rejected our
                # insert, so an ACTIVE row must exist. If it doesn't, the
                # constraint and SELECT are inconsistent — surface that.
                raise PersistenceError(
                    "get_or_create_session: INSERT hit ON CONFLICT but no "
                    f"ACTIVE session found for {platform}/{platform_user}. "
                    "Index ux_sessions_active_user may be missing or stale."
                )
            await conn.execute(
                sa.update(sessions)
                .where(sessions.c.id == row.id)
                .values(last_active_at=utcnow())
            )
            await conn.commit()
            return self._row_to_session(row)

    @staticmethod
    def _build_active_session_upsert(dialect_name: str, values: dict[str, Any]) -> Any:
        """Build an INSERT ... ON CONFLICT DO NOTHING for the active-session index.

        Returns a statement that inserts ``values`` into ``sessions`` and, on
        conflict with ``ux_sessions_active_user``, does nothing. The statement
        also has a RETURNING clause for ``id`` so the caller can distinguish
        "we won" (one row returned) from "we lost the race" (zero rows).
        """
        if dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            sqlite_stmt = sqlite_insert(sessions).values(**values)
            sqlite_stmt = sqlite_stmt.on_conflict_do_nothing(
                index_elements=["platform", "platform_user"],
                # Must match the partial index's WHERE exactly; persisted
                # value is lowercase ``SessionState.ACTIVE.value``.
                index_where=sa.text("state = 'active'"),
            )
            return sqlite_stmt.returning(sessions.c.id)
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_stmt = pg_insert(sessions).values(**values)
            pg_stmt = pg_stmt.on_conflict_do_nothing(
                index_elements=["platform", "platform_user"],
                index_where=sa.text("state = 'active'"),
            )
            return pg_stmt.returning(sessions.c.id)
        raise PersistenceError(
            f"get_or_create_session: dialect {dialect_name!r} not supported. "
            "Hestia ships dialect-aware upserts only for sqlite and postgresql."
        )

    async def archive_session(
        self, session_id: str, summary: str | None = None
    ) -> None:
        """Mark a session as ARCHIVED and generate a handoff record.

        Args:
            session_id: The session to archive.
            summary: Optional summary text from the handoff summarizer (L158).
        """
        session = await self.get_session(session_id)

        update = (
            sa.update(sessions)
            .where(sessions.c.id == session_id)
            .values(
                state=SessionState.ARCHIVED.value,
                last_active_at=utcnow(),
            )
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

        if session is not None:
            try:
                await self._generate_and_save_handoff(session, summary)
            except Exception:  # noqa: BLE001 — best-effort handoff
                logger.warning(
                    "Failed to generate handoff for %s", session_id, exc_info=True
                )

    async def create_session(
        self,
        platform: str,
        platform_user: str,
        archive_previous: Session | None = None,
    ) -> Session:
        """Create a new session row. Optionally archives a previous session.

        Used by /reset and similar flows where the caller explicitly wants a
        fresh session for an existing user.

        Args:
            platform: Platform identifier (e.g., "cli", "matrix")
            platform_user: User identifier on that platform
            archive_previous: If provided, archive this session before creating
                the new one so we never end up with two ACTIVE sessions for the
                same user. The partial unique index ``ux_sessions_active_user``
                guards against races.
        """
        if archive_previous is not None:
            await self.archive_session(archive_previous.id)

        session_id = _generate_session_id(platform, platform_user)
        now = utcnow()
        new_session = Session(
            id=session_id,
            platform=platform,
            platform_user=platform_user,
            started_at=now,
            last_active_at=now,
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        insert = sa.insert(sessions).values(
            id=new_session.id,
            platform=new_session.platform,
            platform_user=new_session.platform_user,
            started_at=new_session.started_at,
            last_active_at=new_session.last_active_at,
            slot_id=new_session.slot_id,
            slot_saved_path=new_session.slot_saved_path,
            state=new_session.state.value,
            temperature=new_session.temperature.value,
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

        if self._event_bus is not None:
            await self._event_bus.publish(
                "session_started",
                {
                    "session_id": new_session.id,
                    "platform": platform,
                    "platform_user": platform_user,
                },
            )

        return new_session

    async def get_or_create_session_with_handoff(
        self, platform: str, platform_user: str
    ) -> Session:
        """Get or create a session, injecting a handoff if the session is new.

        After ``get_or_create_session`` returns, we check whether the session
        already has messages. If it does not, we look for the most recent
        handoff for this user and prepend a synthetic system message so the
        new session retains continuity context.
        """
        session = await self.get_or_create_session(platform, platform_user)
        existing = await self.get_messages(session.id)
        if not existing:
            handoff = await self.get_latest_handoff(platform, platform_user)
            if handoff is not None:
                synthetic = Message(
                    role="user",
                    content=self._format_handoff_message(handoff),
                )
                await self.append_message(session.id, synthetic)
        return session

    def _format_handoff_message(self, handoff: SessionHandoff) -> str:
        """Build a synthetic system message from a handoff record."""
        parts: list[str] = ["[Previous session context]"]
        if handoff.summary:
            parts.append(f"Summary: {handoff.summary}")
        if handoff.key_messages:
            parts.append("Recent messages:")
            for msg in handoff.key_messages:
                content = msg.get("content", "")
                # Truncate very long messages to keep the handoff compact
                if len(content) > 500:
                    content = content[:500].rstrip() + "…"
                parts.append(f"  {msg.get('role', 'unknown')}: {content}")
        if handoff.artifacts:
            parts.append(f"Artifacts: {', '.join(handoff.artifacts)}")
        return "\n".join(parts)

    # --- Handoff persistence ---

    async def save_handoff(self, session_id: str, handoff: SessionHandoff) -> None:
        """Persist a SessionHandoff record."""
        from hestia.persistence.schema import session_handoffs

        insert = sa.insert(session_handoffs).values(
            id=str(uuid.uuid4()),
            previous_session_id=handoff.previous_session_id,
            platform=handoff.platform,
            platform_user=handoff.platform_user,
            summary=handoff.summary,
            key_messages=json.dumps(handoff.key_messages),
            artifacts=json.dumps(handoff.artifacts),
            created_at=handoff.created_at,
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

    async def get_latest_handoff(
        self, platform: str, platform_user: str
    ) -> SessionHandoff | None:
        """Return the most recent handoff for a user, or None."""
        from hestia.persistence.schema import session_handoffs

        query = (
            sa.select(session_handoffs)
            .where(
                sa.and_(
                    session_handoffs.c.platform == platform,
                    session_handoffs.c.platform_user == platform_user,
                )
            )
            .order_by(session_handoffs.c.created_at.desc())
            .limit(1)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return SessionHandoff(
                previous_session_id=row.previous_session_id,
                platform=row.platform,
                platform_user=row.platform_user,
                summary=row.summary or "",
                key_messages=json.loads(row.key_messages) if row.key_messages else [],
                artifacts=json.loads(row.artifacts) if row.artifacts else [],
                created_at=row.created_at,
            )

    async def list_handoffs_for_identities(
        self, identity_tuples: list[tuple[str, str]], limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return recent handoffs for a list of (platform, platform_user) identities."""
        from hestia.persistence.schema import session_handoffs

        if not identity_tuples:
            return []

        conditions = [
            sa.and_(
                session_handoffs.c.platform == platform,
                session_handoffs.c.platform_user == platform_user,
            )
            for platform, platform_user in identity_tuples
        ]

        query = (
            sa.select(session_handoffs)
            .where(sa.or_(*conditions))
            .order_by(session_handoffs.c.created_at.desc())
            .limit(limit)
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [
                {
                    "session_id": row.previous_session_id,
                    "summary": row.summary or "",
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def _extract_artifact_handles(self, messages: list[Message]) -> list[str]:
        """Scan message content for artifact handle references."""
        handles: set[str] = set()
        for msg in messages:
            if msg.content:
                handles.update(_ARTIFACT_HANDLE_RE.findall(msg.content))
        return sorted(handles)

    async def _generate_and_save_handoff(
        self, session: Session, summary: str | None = None
    ) -> None:
        """Capture the final state of a session and persist a handoff."""
        messages = await self.get_messages(session.id)
        key_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ][-8:]
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
        await self.save_handoff(session.id, handoff)

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        query = sa.select(sessions).where(sessions.c.id == session_id)

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                return self._row_to_session(row)
            return None

    async def get_sessions_batch(self, session_ids: list[str]) -> list[Session]:
        """Get multiple sessions by ID in a single query."""
        if not session_ids:
            return []
        query = sa.select(sessions).where(sessions.c.id.in_(session_ids))

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_session(row) for row in rows]

    async def append_message(self, session_id: str, msg: Message) -> None:
        """Append a message with auto-incrementing idx. Updates last_active_at.

        Race-safe: the SELECT MAX(idx)+1 → INSERT pair is vulnerable to
        concurrent writers producing the same idx, which the
        ``(session_id, idx)`` primary key then rejects with
        ``IntegrityError``. We retry on collision up to
        ``_APPEND_IDX_MAX_ATTEMPTS`` times with exponential backoff so
        the collision resolves naturally: each retry re-reads MAX(idx)
        inside a fresh connection after the winning writer has committed.
        Works on both SQLite and PostgreSQL without dialect-specific
        locking. Regression coverage lives in
        ``tests/unit/test_append_message_race.py``.
        """
        idx_query = sa.select(sa.func.coalesce(sa.func.max(messages.c.idx), -1) + 1).where(
            messages.c.session_id == session_id
        )

        tool_calls_json = None
        if msg.tool_calls:
            tool_calls_json = json.dumps(
                [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                    for tc in msg.tool_calls
                ]
            )

        for attempt in range(_APPEND_IDX_MAX_ATTEMPTS):
            try:
                async with self._db.engine.connect() as conn:
                    idx_result = await conn.execute(idx_query)
                    idx = idx_result.scalar_one()

                    insert = sa.insert(messages).values(
                        session_id=session_id,
                        idx=idx,
                        role=msg.role,
                        content=msg.content,
                        tool_calls=tool_calls_json,
                        tool_call_id=msg.tool_call_id,
                        reasoning_content=msg.reasoning_content,
                        created_at=msg.created_at if msg.created_at else utcnow(),
                    )
                    await conn.execute(insert)

                    update = (
                        sa.update(sessions)
                        .where(sessions.c.id == session_id)
                        .values(last_active_at=utcnow())
                    )
                    await conn.execute(update)
                    await conn.commit()
                    return
            except IntegrityError:
                if attempt == _APPEND_IDX_MAX_ATTEMPTS - 1:
                    raise
                logger.debug(
                    "append_message idx collision for session %s on attempt %d; retrying",
                    session_id,
                    attempt + 1,
                )
                await asyncio.sleep(0.001 * (2**attempt))

    async def get_messages(self, session_id: str) -> list[Message]:
        """Get all messages for a session in order."""
        query = (
            sa.select(messages).where(messages.c.session_id == session_id).order_by(messages.c.idx)
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_message(row) for row in rows]

    async def end_session(self, session_id: str, reason: str) -> None:
        """Mark a session as archived."""
        update = (
            sa.update(sessions)
            .where(sessions.c.id == session_id)
            .values(
                state=SessionState.ARCHIVED.value,
                last_active_at=utcnow(),
            )
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def assign_slot(
        self,
        session_id: str,
        slot_id: int,
        clear_saved_path: bool = False,
    ) -> None:
        """Assign a live slot to a session and mark it hot.

        Args:
            session_id: Which session
            slot_id: Live slot index on the inference server
            clear_saved_path: If True, also clear slot_saved_path. Use when the
                session was WARM (disk-backed) and we've now restored into a
                live slot, so the disk path is stale.
        """
        values = {
            "slot_id": slot_id,
            "temperature": SessionTemperature.HOT.value,
            "last_active_at": utcnow(),
        }
        if clear_saved_path:
            values["slot_saved_path"] = None
        update = sa.update(sessions).where(sessions.c.id == session_id).values(**values)

        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def release_slot(
        self,
        session_id: str,
        demote_to: SessionTemperature = SessionTemperature.WARM,
        saved_path: str | None = None,
    ) -> None:
        """Release the slot and record the disk path where its state lives.

        Args:
            session_id: Which session to release
            demote_to: Target temperature (WARM if we saved to disk, COLD if we erased)
            saved_path: If demoting to WARM, the path on disk where slot state was saved
        """
        update = (
            sa.update(sessions)
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

    async def update_saved_path(self, session_id: str, saved_path: str) -> None:
        """Update just the slot_saved_path field. Used after slot_save checkpoint."""
        update = (
            sa.update(sessions)
            .where(sessions.c.id == session_id)
            .values(slot_saved_path=saved_path)
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    def _row_to_session(self, row: Any) -> Session:
        """Convert a database row to a Session dataclass."""
        return Session(
            id=row.id,
            platform=row.platform,
            platform_user=row.platform_user,
            started_at=row.started_at,
            last_active_at=row.last_active_at,
            slot_id=row.slot_id,
            slot_saved_path=row.slot_saved_path,
            state=SessionState(row.state),
            temperature=SessionTemperature(row.temperature),
        )

    def _row_to_message(self, row: Any) -> Message:
        """Convert a database row to a Message dataclass."""
        tool_calls = None
        if row.tool_calls:
            try:
                data = json.loads(row.tool_calls)
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=tc["arguments"],
                    )
                    for tc in data
                ]
            except (json.JSONDecodeError, KeyError) as e:
                raise PersistenceError(f"Failed to parse tool_calls JSON: {e}") from e

        return Message(
            role=row.role,
            content=row.content,
            tool_calls=tool_calls,
            tool_call_id=row.tool_call_id,
            reasoning_content=row.reasoning_content,
            created_at=row.created_at,
        )

    # --- Turn persistence ---

    async def insert_turn(self, turn: Turn) -> None:
        """Insert a new turn into the database."""
        from hestia.persistence.schema import turns

        insert = sa.insert(turns).values(
            id=turn.id,
            session_id=turn.session_id,
            state=turn.state.value,
            started_at=turn.started_at,
            last_transition_at=turn.started_at,
            iteration=turn.iterations,
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

    async def update_turn(self, turn: Turn) -> None:
        """Update a turn's state and completion info."""
        from hestia.persistence.schema import turns

        update = (
            sa.update(turns)
            .where(turns.c.id == turn.id)
            .values(
                state=turn.state.value,
                last_transition_at=utcnow(),
                iteration=turn.iterations,
                error=turn.error,
            )
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def append_transition(self, turn_id: str, transition: TurnTransition) -> None:
        """Append a transition to the turn_transitions table.

        Race-safe via the same retry-on-IntegrityError pattern used by
        :meth:`append_message`. Two concurrent state machine transitions on
        the same turn (e.g. a cancellation racing a completion) would
        otherwise collide on the ``(turn_id, idx)`` primary key.
        """
        from hestia.persistence.schema import turn_transitions

        idx_query = sa.select(sa.func.coalesce(sa.func.max(turn_transitions.c.idx), -1) + 1).where(
            turn_transitions.c.turn_id == turn_id
        )

        for attempt in range(_APPEND_IDX_MAX_ATTEMPTS):
            try:
                async with self._db.engine.connect() as conn:
                    idx_result = await conn.execute(idx_query)
                    idx = idx_result.scalar_one()

                    insert = sa.insert(turn_transitions).values(
                        turn_id=turn_id,
                        idx=idx,
                        from_state=transition.from_state.value,
                        to_state=transition.to_state.value,
                        at=transition.at,
                        reason=transition.note,
                    )
                    await conn.execute(insert)
                    await conn.commit()
                    return
            except IntegrityError:
                if attempt == _APPEND_IDX_MAX_ATTEMPTS - 1:
                    raise
                logger.debug(
                    "append_transition idx collision for turn %s on attempt %d; retrying",
                    turn_id,
                    attempt + 1,
                )
                await asyncio.sleep(0.001 * (2**attempt))

    async def get_turn(self, turn_id: str) -> Turn | None:
        """Get a turn by ID (without transitions)."""
        from hestia.orchestrator.types import Turn, TurnState
        from hestia.persistence.schema import turns

        query = sa.select(turns).where(turns.c.id == turn_id)

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                return Turn(
                    id=row.id,
                    session_id=row.session_id,
                    state=TurnState(row.state),
                    user_message=None,  # Not stored in turns table
                    started_at=row.started_at,
                    completed_at=None,  # Not tracked separately
                    iterations=row.iteration,
                    tool_calls_made=0,  # Not stored separately
                    final_response=None,
                    error=row.error,
                    transitions=[],  # Loaded separately
                )
            return None

    async def list_turns_for_session(self, session_id: str, limit: int = 50) -> list[Turn]:
        """List turns for a session, newest first."""
        from hestia.orchestrator.types import Turn, TurnState
        from hestia.persistence.schema import turns

        query = (
            sa.select(turns)
            .where(turns.c.session_id == session_id)
            .order_by(turns.c.started_at.desc())
            .limit(limit)
        )

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [
                Turn(
                    id=row.id,
                    session_id=row.session_id,
                    state=TurnState(row.state),
                    user_message=None,
                    started_at=row.started_at,
                    completed_at=None,
                    iterations=row.iteration,
                    tool_calls_made=0,
                    final_response=None,
                    error=row.error,
                    transitions=[],
                )
                for row in rows
            ]

    async def list_stale_turns(self) -> list[Turn]:
        """List all turns not in a terminal state. Used for crash recovery."""
        from hestia.orchestrator.types import Turn, TurnState
        from hestia.persistence.schema import turns

        terminal_states = ["done", "failed"]
        query = sa.select(turns).where(sa.not_(turns.c.state.in_(terminal_states)))

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [
                Turn(
                    id=row.id,
                    session_id=row.session_id,
                    state=TurnState(row.state),
                    user_message=None,
                    started_at=row.started_at,
                    completed_at=None,
                    iterations=row.iteration,
                    tool_calls_made=0,
                    final_response=None,
                    error=row.error,
                    transitions=[],
                )
                for row in rows
            ]

    async def fail_turn(self, turn_id: str, error: str) -> None:
        """Force a turn into FAILED state. Used for crash recovery."""
        from hestia.persistence.schema import turns

        update = (
            sa.update(turns)
            .where(turns.c.id == turn_id)
            .values(
                state="failed",
                error=error,
                last_transition_at=utcnow(),
            )
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def count_turns_for_session(self, session_id: str) -> int:
        """Count turns for a session."""
        from hestia.persistence.schema import turns

        query = sa.select(sa.func.count(turns.c.id)).where(turns.c.session_id == session_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            return result.scalar_one() or 0

    async def list_sessions(
        self, limit: int = 20, platform: str | None = None, platform_user: str | None = None
    ) -> list[Session]:
        """List recent sessions ordered by last activity.

        Args:
            limit: Maximum number of sessions to return.
            platform: Optional platform filter.
            platform_user: Optional platform user filter.

        Returns:
            List of sessions, most recently active first.
        """
        conditions = []
        if platform is not None:
            conditions.append(sessions.c.platform == platform)
        if platform_user is not None:
            conditions.append(sessions.c.platform_user == platform_user)

        query = sa.select(sessions).order_by(sessions.c.last_active_at.desc()).limit(limit)
        if conditions:
            query = query.where(sa.and_(*conditions))

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_session(row) for row in rows]

    # --- Stats queries for CLI status command ---

    async def count_sessions_by_state(self) -> dict[str, int]:
        """Count sessions grouped by state.

        Returns:
            Dict mapping state name to count.
        """
        query = sa.select(sessions.c.state, sa.func.count(sessions.c.id)).group_by(sessions.c.state)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return {row.state: row[1] for row in rows}

    async def turn_stats_since(self, since: datetime) -> dict[str, int]:
        """Count turns by terminal state since a given time.

        Args:
            since: Only count turns started at or after this time.

        Returns:
            Dict mapping state name to count (only includes terminal states
            that have at least one turn).
        """
        from hestia.persistence.schema import turns

        query = (
            sa.select(turns.c.state, sa.func.count(turns.c.id))
            .where(
                sa.and_(
                    turns.c.started_at >= since,
                    turns.c.state.in_(["done", "failed"]),
                )
            )
            .group_by(turns.c.state)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return {row.state: row[1] for row in rows}
