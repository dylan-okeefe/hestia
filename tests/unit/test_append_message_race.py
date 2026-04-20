"""Regression tests for SessionStore.append_message / append_transition races.

Pre-v0.9.0, these two methods did a ``SELECT MAX(idx) + 1`` followed by an
``INSERT`` inside a single ``async with connect()`` but without taking a
write lock upfront, so two concurrent callers could both compute the same
idx and both attempt to INSERT. The second INSERT hit the
``PRIMARY KEY (session_id, idx)`` constraint and raised ``IntegrityError``,
losing the message.

The v0.9.0 fix (Copilot audit C-2) adds a retry-on-IntegrityError loop:
on collision the writer backs off briefly and re-reads MAX(idx), which by
then reflects the other writer's committed insert. These tests spawn 20
concurrent appenders against the same session / turn and assert every
caller's row landed with a distinct idx and no ``IntegrityError`` escaped.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.core.types import Message, SessionState, SessionTemperature
from hestia.core.types import Session as HestiaSession
from hestia.orchestrator.types import TurnState, TurnTransition
from hestia.persistence.db import Database
from hestia.persistence.schema import messages, sessions, turn_transitions, turns
from hestia.persistence.sessions import SessionStore


@pytest.fixture
async def store(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/append_race.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    yield SessionStore(db)
    await db.close()


async def _seed_session(store: SessionStore, session_id: str) -> None:
    session = HestiaSession(
        id=session_id,
        platform="test",
        platform_user="user",
        started_at=utcnow(),
        last_active_at=utcnow(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    values = {
        "id": session.id,
        "platform": session.platform,
        "platform_user": session.platform_user,
        "started_at": session.started_at,
        "last_active_at": session.last_active_at,
        "slot_id": session.slot_id,
        "slot_saved_path": session.slot_saved_path,
        "state": session.state.value,
        "temperature": session.temperature.value,
    }
    async with store._db.engine.connect() as conn:  # noqa: SLF001 — test bootstrap
        await conn.execute(sa.insert(sessions).values(**values))
        await conn.commit()


async def _seed_turn(store: SessionStore, turn_id: str, session_id: str) -> None:
    values = {
        "id": turn_id,
        "session_id": session_id,
        "state": TurnState.RECEIVED.value,
        "started_at": utcnow(),
        "last_transition_at": utcnow(),
        "iteration": 0,
        "error": None,
    }
    async with store._db.engine.connect() as conn:  # noqa: SLF001
        await conn.execute(sa.insert(turns).values(**values))
        await conn.commit()


@pytest.mark.asyncio
async def test_append_message_concurrent_20_no_collision(store: SessionStore) -> None:
    """20 concurrent append_message calls on the same session yield 20 distinct idx."""
    session_id = f"s_{uuid.uuid4().hex[:8]}"
    await _seed_session(store, session_id)

    async def _append(i: int) -> None:
        msg = Message(role="user", content=f"msg-{i}", created_at=utcnow())
        await store.append_message(session_id, msg)

    await asyncio.gather(*(_append(i) for i in range(20)))

    async with store._db.engine.connect() as conn:  # noqa: SLF001
        result = await conn.execute(
            sa.select(messages.c.idx).where(messages.c.session_id == session_id)
        )
        idxs = sorted(row.idx for row in result.fetchall())

    assert len(idxs) == 20, f"expected 20 rows, got {len(idxs)}"
    assert idxs == list(range(20)), f"expected distinct idx 0..19, got {idxs}"


@pytest.mark.asyncio
async def test_append_transition_concurrent_20_no_collision(store: SessionStore) -> None:
    """20 concurrent append_transition calls on the same turn yield 20 distinct idx."""
    session_id = f"s_{uuid.uuid4().hex[:8]}"
    turn_id = f"t_{uuid.uuid4().hex[:8]}"
    await _seed_session(store, session_id)
    await _seed_turn(store, turn_id, session_id)

    async def _append(i: int) -> None:
        transition = TurnTransition(
            from_state=TurnState.RECEIVED,
            to_state=TurnState.DONE,
            at=utcnow(),
            note=f"transition-{i}",
        )
        await store.append_transition(turn_id, transition)

    await asyncio.gather(*(_append(i) for i in range(20)))

    async with store._db.engine.connect() as conn:  # noqa: SLF001
        result = await conn.execute(
            sa.select(turn_transitions.c.idx).where(turn_transitions.c.turn_id == turn_id)
        )
        idxs = sorted(row.idx for row in result.fetchall())

    assert len(idxs) == 20
    assert idxs == list(range(20))
