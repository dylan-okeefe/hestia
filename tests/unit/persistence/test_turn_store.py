"""Unit tests for TurnStore."""

from datetime import datetime

import pytest

from hestia.orchestrator.mappers import turn_domain_to_dto
from hestia.orchestrator.types import Turn, TurnState
from hestia.persistence.db import Database
from hestia.persistence.session_store import SessionStore
from hestia.persistence.turn_store import TurnStore


@pytest.fixture
async def db(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    yield db
    await db.close()


@pytest.fixture
async def session_store(db):
    return SessionStore(db)


@pytest.fixture
async def turn_store(db):
    return TurnStore(db)


@pytest.mark.asyncio
async def test_insert_and_get_turn(turn_store, session_store):
    """Can persist a turn and read it back."""
    session = await session_store.create_session("test", "user1")
    turn = Turn(
        id="turn_1",
        session_id=session.id,
        state=TurnState.RECEIVED,
        user_message=None,
        started_at=datetime.now(),
        iterations=0,
    )
    await turn_store.insert_turn(turn_domain_to_dto(turn))

    loaded = await turn_store.get_turn(turn.id)
    assert loaded is not None
    assert loaded.id == turn.id
    assert loaded.state == TurnState.RECEIVED.value


@pytest.mark.asyncio
async def test_update_turn(turn_store, session_store):
    """update_turn modifies an existing turn row."""
    session = await session_store.create_session("test", "user2")
    turn = Turn(
        id="turn_2",
        session_id=session.id,
        state=TurnState.RECEIVED,
        user_message=None,
        started_at=datetime.now(),
        iterations=0,
    )
    await turn_store.insert_turn(turn_domain_to_dto(turn))

    turn.state = TurnState.DONE
    turn.iterations = 2
    await turn_store.update_turn(turn_domain_to_dto(turn))

    loaded = await turn_store.get_turn(turn.id)
    assert loaded.state == TurnState.DONE.value
    assert loaded.iteration == 2


@pytest.mark.asyncio
async def test_fail_turn(turn_store, session_store):
    """fail_turn marks the turn failed and records the error."""
    session = await session_store.create_session("test", "user3")
    turn = Turn(
        id="turn_3",
        session_id=session.id,
        state=TurnState.RECEIVED,
        user_message=None,
        started_at=datetime.now(),
    )
    await turn_store.insert_turn(turn_domain_to_dto(turn))

    await turn_store.fail_turn(turn.id, "boom")

    loaded = await turn_store.get_turn(turn.id)
    assert loaded.state == "failed"
    assert loaded.error == "boom"


@pytest.mark.asyncio
async def test_count_turns_for_sessions(turn_store, session_store):
    """Counts are returned for requested session ids, zero for empty inputs."""
    session1 = await session_store.create_session("test", "u1")
    session2 = await session_store.create_session("test", "u2")

    for i in range(2):
        await turn_store.insert_turn(
            turn_domain_to_dto(
                Turn(
                    id=f"t1_{i}",
                    session_id=session1.id,
                    state=TurnState.DONE,
                    user_message=None,
                    started_at=datetime.now(),
                )
            )
        )

    assert await turn_store.count_turns_for_session(session1.id) == 2
    assert await turn_store.count_turns_for_session(session2.id) == 0
    assert await turn_store.count_turns_for_sessions([]) == {}
    counts = await turn_store.count_turns_for_sessions([session1.id, session2.id])
    assert counts == {session1.id: 2, session2.id: 0}
