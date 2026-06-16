"""Round-trip tests for Turn domain <-> persistence DTO mapping."""

from datetime import datetime

import pytest

from hestia.core.types import Message
from hestia.orchestrator.mappers import turn_domain_to_dto, turn_dto_to_domain
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
async def test_turn_dto_roundtrip(turn_store, session_store):
    """A rich Turn survives mapping to DTO, persistence, and back."""
    session = await session_store.create_session("test", "user1")
    original = Turn(
        id="turn_123",
        session_id=session.id,
        state=TurnState.DONE,
        user_message=Message(role="user", content="hi"),
        started_at=datetime.now(),
        completed_at=datetime.now(),
        iterations=3,
        tool_calls_made=2,
        final_response="done",
        error=None,
        reasoning_budget=8192,
        status_msg_id="status_1",
        slot_id=7,
        thinking_aborted=False,
        artifact_handles=["art_abc1234567"],
    )

    dto = turn_domain_to_dto(original)
    await turn_store.insert_turn(dto)

    loaded_dto = await turn_store.get_turn(original.id)
    assert loaded_dto is not None
    restored = turn_dto_to_domain(loaded_dto)

    assert restored.id == original.id
    assert restored.session_id == original.session_id
    assert restored.state == original.state
    assert restored.iterations == original.iterations
    assert restored.reasoning_budget == original.reasoning_budget
    assert restored.status_msg_id == original.status_msg_id
    assert restored.slot_id == original.slot_id
    assert restored.error == original.error


@pytest.mark.asyncio
async def test_turn_dto_reconstructs_non_persisted_defaults(turn_store, session_store):
    """Fields not stored in the turns table are reconstructed with safe defaults."""
    session = await session_store.create_session("test", "user2")
    original = Turn(
        id="turn_456",
        session_id=session.id,
        state=TurnState.RECEIVED,
        user_message=None,
        started_at=datetime.now(),
        iterations=5,
        tool_calls_made=9,
        final_response="should not persist",
        thinking_aborted=True,
        artifact_handles=["art_should_not_persist"],
    )

    await turn_store.insert_turn(turn_domain_to_dto(original))
    restored = turn_dto_to_domain(await turn_store.get_turn(original.id))

    assert restored.completed_at is None
    assert restored.tool_calls_made == 0
    assert restored.final_response is None
    assert restored.thinking_aborted is False
    assert restored.artifact_handles == []
    assert restored.transitions == []
