"""Round-trip tests for Message domain <-> persistence DTO mapping."""

from datetime import datetime

import pytest

from hestia.core.types import Message, ToolCall
from hestia.orchestrator.mappers import message_domain_to_dto, message_dto_to_domain
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


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
async def message_store(db):
    return MessageStore(db)


@pytest.mark.asyncio
async def test_message_dto_roundtrip(message_store, session_store):
    """A rich Message survives mapping to DTO, persistence, and back."""
    session = await session_store.create_session("test", "user1")
    original = Message(
        role="user",
        content="Hello, world!",
        tool_calls=[
            ToolCall(id="call_1", name="current_time", arguments={"timezone": "UTC"})
        ],
        tool_call_id="call_1",
        reasoning_content="<thinking>Now</thinking>",
        is_handoff=False,
        correction=True,
    )

    dto = message_domain_to_dto(original, session.id, idx=0)
    await message_store.append_message(session.id, dto)

    loaded_dtos = await message_store.get_messages(session.id)
    assert len(loaded_dtos) == 1
    restored = message_dto_to_domain(loaded_dtos[0])

    assert restored.role == original.role
    assert restored.content == original.content
    assert restored.tool_call_id == original.tool_call_id
    assert restored.reasoning_content == original.reasoning_content
    assert restored.is_handoff == original.is_handoff
    assert restored.correction == original.correction
    assert restored.tool_calls is not None
    assert len(restored.tool_calls) == 1
    assert restored.tool_calls[0].id == original.tool_calls[0].id
    assert restored.tool_calls[0].name == original.tool_calls[0].name
    assert restored.tool_calls[0].arguments == original.tool_calls[0].arguments


@pytest.mark.asyncio
async def test_message_dto_ignores_non_persisted_fields(message_store, session_store):
    """created_at and session-scoped idx are not round-tripped on the domain object."""
    session = await session_store.create_session("test", "user2")
    original = Message(
        role="assistant",
        content="Hi",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    dto = message_domain_to_dto(original, session.id, idx=7)
    await message_store.append_message(session.id, dto)

    loaded = (await message_store.get_messages(session.id))[0]
    restored = message_dto_to_domain(loaded)

    assert restored.content == original.content
    assert restored.created_at != original.created_at
    assert loaded.idx == 0
