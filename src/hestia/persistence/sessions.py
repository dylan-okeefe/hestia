"""Session persistence layer."""

import json
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from hestia.core.types import (
    Message,
    Session,
    SessionState,
    SessionTemperature,
    ToolCall,
)
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.schema import messages, sessions


def _generate_session_id(platform: str, platform_user: str) -> str:
    """Generate a sortable, debuggable session ID."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{platform}_{platform_user}_{timestamp}_{short_uuid}"


class SessionStore:
    """Typed CRUD wrapper for session persistence."""

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db

    async def get_or_create_session(self, platform: str, platform_user: str) -> Session:
        """Get existing active session or create a new one."""
        # Try to find existing active session
        query = (
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

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()

            if row:
                # Update last_active_at
                update = (
                    sa.update(sessions)
                    .where(sessions.c.id == row.id)
                    .values(last_active_at=datetime.now())
                )
                await conn.execute(update)
                await conn.commit()
                return self._row_to_session(row)

        # Create new session
        session_id = _generate_session_id(platform, platform_user)
        now = datetime.now()
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

        return new_session

    async def archive_session(self, session_id: str) -> None:
        """Mark a session as ARCHIVED. Used when /reset creates a successor."""
        update = (
            sa.update(sessions)
            .where(sessions.c.id == session_id)
            .values(
                state=SessionState.ARCHIVED.value,
                last_active_at=datetime.now(),
            )
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def create_session(
        self,
        platform: str,
        platform_user: str,
        archive_previous: Session | None = None,
    ) -> Session:
        """Create a new session row. Optionally archives a previous session atomically.

        Used by /reset and similar flows where the caller explicitly wants a
        fresh session for an existing user.

        Args:
            platform: Platform identifier (e.g., "cli", "matrix")
            platform_user: User identifier on that platform
            archive_previous: If provided, archive this session in the same transaction
                so we never end up with two ACTIVE sessions for the same user.
        """
        session_id = _generate_session_id(platform, platform_user)
        now = datetime.now()
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
            if archive_previous is not None:
                await conn.execute(
                    sa.update(sessions)
                    .where(sessions.c.id == archive_previous.id)
                    .values(state=SessionState.ARCHIVED.value, last_active_at=datetime.now())
                )
            await conn.execute(insert)
            await conn.commit()

        return new_session

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        query = sa.select(sessions).where(sessions.c.id == session_id)

        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                return self._row_to_session(row)
            return None

    async def append_message(self, session_id: str, msg: Message) -> None:
        """Append a message with auto-incrementing idx. Updates last_active_at."""
        # Get next idx
        idx_query = sa.select(sa.func.coalesce(sa.func.max(messages.c.idx), -1) + 1).where(
            messages.c.session_id == session_id
        )

        # Serialize tool_calls to JSON if present
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
                created_at=msg.created_at if msg.created_at else datetime.now(),
            )
            await conn.execute(insert)

            # Update session last_active_at
            update = (
                sa.update(sessions)
                .where(sessions.c.id == session_id)
                .values(last_active_at=datetime.now())
            )
            await conn.execute(update)
            await conn.commit()

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
                last_active_at=datetime.now(),
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
            "last_active_at": datetime.now(),
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
                last_active_at=datetime.now(),
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

    async def insert_turn(self, turn: "Turn") -> None:
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

    async def update_turn(self, turn: "Turn") -> None:
        """Update a turn's state and completion info."""
        from hestia.persistence.schema import turns

        update = (
            sa.update(turns)
            .where(turns.c.id == turn.id)
            .values(
                state=turn.state.value,
                last_transition_at=datetime.now(),
                iteration=turn.iterations,
                error=turn.error,
            )
        )

        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def append_transition(
        self, turn_id: str, transition: "TurnTransition"
    ) -> None:
        """Append a transition to the turn_transitions table."""
        from hestia.persistence.schema import turn_transitions

        # Get next idx for this turn
        idx_query = (
            sa.select(sa.func.coalesce(sa.func.max(turn_transitions.c.idx), -1) + 1)
            .where(turn_transitions.c.turn_id == turn_id)
        )

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

    async def get_turn(self, turn_id: str) -> "Turn | None":
        """Get a turn by ID (without transitions)."""
        from hestia.persistence.schema import turns
        from hestia.orchestrator.types import Turn, TurnState

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

    async def list_turns_for_session(
        self, session_id: str, limit: int = 50
    ) -> list["Turn"]:
        """List turns for a session, newest first."""
        from hestia.persistence.schema import turns
        from hestia.orchestrator.types import Turn, TurnState

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
