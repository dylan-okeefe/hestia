"""Turn persistence store."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select

from hestia.core.clock import utcnow
from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.dto import TurnDTO, TurnTransitionDTO
from hestia.persistence.schema import turn_transitions, turns

logger = logging.getLogger(__name__)

_TRANSITION_IDX_MAX_ATTEMPTS = 10


class TurnStore:
    """Store for turn and transition state."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def insert_turn(self, turn: TurnDTO) -> None:
        """Insert a new turn."""
        insert = turns.insert().values(
            id=turn.id,
            session_id=turn.session_id,
            state=turn.state,
            started_at=turn.started_at,
            last_transition_at=turn.last_transition_at,
            iteration=turn.iteration,
            reasoning_budget=turn.reasoning_budget,
            status_msg_id=turn.status_msg_id,
            slot_id=turn.slot_id,
            error=turn.error,
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(insert)
            await conn.commit()

    async def update_turn(self, turn: TurnDTO) -> None:
        """Update an existing turn."""
        update = (
            turns.update()
            .where(turns.c.id == turn.id)
            .values(
                state=turn.state,
                last_transition_at=turn.last_transition_at,
                iteration=turn.iteration,
                reasoning_budget=turn.reasoning_budget,
                status_msg_id=turn.status_msg_id,
                slot_id=turn.slot_id,
                error=turn.error,
            )
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def get_turn(self, turn_id: str) -> TurnDTO | None:
        """Fetch a turn by id."""
        query = select(turns).where(turns.c.id == turn_id)
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_turn(row)

    async def list_turns_for_session(
        self, session_id: str, limit: int = 50
    ) -> list[TurnDTO]:
        """Return turns for a session, newest first."""
        query = (
            select(turns)
            .where(turns.c.session_id == session_id)
            .order_by(turns.c.started_at.desc())
            .limit(limit)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_turn(row) for row in rows]

    async def list_stale_turns(
        self, stale_after_minutes: int = 30
    ) -> list[TurnDTO]:
        """Return turns that look stuck in a non-terminal state."""
        # BUG-081: use a tz-aware cutoff matching the aware timestamps written
        # by clock.utcnow(); naive cutoffs degrade to string comparisons.
        cutoff = datetime.now(UTC) - timedelta(minutes=stale_after_minutes)
        terminal_states = {"done", "failed"}
        query = (
            select(turns)
            .where(
                ~turns.c.state.in_(terminal_states)
                & (turns.c.last_transition_at < cutoff)
            )
            .order_by(turns.c.last_transition_at.asc())
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_turn(row) for row in rows]

    async def list_turns_with_errors(self, limit: int = 50) -> list[TurnDTO]:
        """Return recent turns with non-null error."""
        query = (
            select(turns)
            .where(turns.c.error.isnot(None))
            .order_by(turns.c.started_at.desc())
            .limit(limit)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            return [self._row_to_turn(row) for row in rows]

    async def count_turns_for_session(self, session_id: str) -> int:
        """Count total turns for a session."""
        query = select(sa.func.count(turns.c.id)).where(
            turns.c.session_id == session_id
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            return int(result.scalar_one())

    async def count_turns_for_sessions(
        self, session_ids: list[str]
    ) -> dict[str, int]:
        """Count turns for multiple sessions."""
        if not session_ids:
            return {}
        query = (
            select(turns.c.session_id, sa.func.count(turns.c.id))
            .where(turns.c.session_id.in_(session_ids))
            .group_by(turns.c.session_id)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            counts = dict.fromkeys(session_ids, 0)
            counts.update({row.session_id: int(row[1]) for row in rows})
            return counts

    async def turn_stats_since(self, since: datetime) -> dict[str, int]:
        """Return aggregate turn counts since a timestamp."""
        query = (
            select(turns.c.state, sa.func.count(turns.c.id))
            .where(turns.c.started_at >= since)
            .group_by(turns.c.state)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            stats: dict[str, int] = {}
            for state, count in rows:
                stats[state] = int(count)
            return stats

    async def append_transition(self, transition: TurnTransitionDTO) -> None:
        """Append a state transition record with retry on idx collision."""
        for attempt in range(_TRANSITION_IDX_MAX_ATTEMPTS):
            try:
                async with self._db.engine.connect() as conn:
                    idx_query = (
                        select(sa.func.coalesce(sa.func.max(turn_transitions.c.idx), -1) + 1)
                        .where(turn_transitions.c.turn_id == transition.turn_id)
                    )
                    result = await conn.execute(idx_query)
                    idx = result.scalar_one()

                    insert = turn_transitions.insert().values(
                        turn_id=transition.turn_id,
                        idx=idx,
                        from_state=transition.from_state,
                        to_state=transition.to_state,
                        at=transition.at,
                        reason=transition.reason,
                    )
                    await conn.execute(insert)
                    await conn.commit()
                    return
            except sa.exc.IntegrityError:
                logger.debug(
                    "Transition idx collision for turn %s, attempt %d/%d",
                    transition.turn_id,
                    attempt + 1,
                    _TRANSITION_IDX_MAX_ATTEMPTS,
                )
                if attempt == _TRANSITION_IDX_MAX_ATTEMPTS - 1:
                    raise PersistenceError(
                        "Failed to append transition after "
                        f"{_TRANSITION_IDX_MAX_ATTEMPTS} attempts"
                    ) from None
                continue

    async def fail_turn(self, turn_id: str, error: str) -> None:
        """Mark a turn as failed."""
        update = (
            turns.update()
            .where(turns.c.id == turn_id)
            .values(state="failed", error=error, last_transition_at=utcnow())
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(update)
            await conn.commit()

    async def get_turn_messages(self, turn_id: str) -> dict[str, str] | None:
        """Return the latest assistant/user messages for a turn."""
        from hestia.persistence.schema import messages

        query = (
            select(messages.c.role, messages.c.content)
            .join(turns, messages.c.session_id == turns.c.session_id)
            .where(turns.c.id == turn_id)
            .order_by(messages.c.idx.desc())
            .limit(20)
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
            if not rows:
                return None
            return {row.role: row.content for row in rows}

    def _row_to_turn(self, row: Any) -> TurnDTO:
        return TurnDTO(
            id=row.id,
            session_id=row.session_id,
            state=row.state,
            started_at=row.started_at,
            last_transition_at=row.last_transition_at,
            iteration=row.iteration,
            reasoning_budget=row.reasoning_budget,
            status_msg_id=row.status_msg_id,
            slot_id=row.slot_id,
            error=row.error,
        )
