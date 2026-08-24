"""Unit tests for MessageStore."""

import pytest

from hestia.core.clock import utcnow
from hestia.core.types import Message
from hestia.orchestrator.mappers import message_domain_to_dto
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
async def test_append_message_bumps_last_active_at(message_store, session_store):
    """Appending a message updates the parent session's last_active_at."""
    session = await session_store.create_session("test", "user1")
    before = (await session_store.get_session(session.id)).last_active_at

    await message_store.append_message(
        session.id,
        message_domain_to_dto(
            Message(role="user", content="hello", created_at=utcnow()),
            session.id,
            idx=0,
        ),
    )

    updated = await session_store.get_session(session.id)
    assert updated.last_active_at > before


@pytest.mark.asyncio
async def test_append_message_uses_write_time_not_message_time(
    message_store, session_store
):
    """last_active_at must reflect the append write time, not msg.created_at."""
    from datetime import timedelta

    session = await session_store.create_session("test", "user1")
    before = (await session_store.get_session(session.id)).last_active_at
    past = (utcnow() - timedelta(seconds=5)).replace(tzinfo=None)

    await message_store.append_message(
        session.id,
        message_domain_to_dto(
            Message(role="user", content="delayed", created_at=past),
            session.id,
            idx=0,
        ),
    )

    updated = await session_store.get_session(session.id)
    assert updated.last_active_at > before
    assert updated.last_active_at > past


@pytest.mark.asyncio
async def test_get_messages_ordered_by_idx(message_store, session_store):
    """Messages are returned in insertion order."""
    session = await session_store.create_session("test", "user2")
    for _i, content in enumerate(["first", "second", "third"]):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user", content=content), session.id, idx=0
            ),
        )

    messages = await message_store.get_messages(session.id)
    assert [m.content for m in messages] == ["first", "second", "third"]
    assert [m.idx for m in messages] == [0, 1, 2]


@pytest.mark.asyncio
async def test_get_handoff_messages_only(message_store, session_store):
    """get_handoff_messages filters to is_handoff=True rows."""
    session = await session_store.create_session("test", "user3")
    await message_store.append_message(
        session.id,
        message_domain_to_dto(
            Message(role="user", content="regular"), session.id, idx=0
        ),
    )
    await message_store.append_message(
        session.id,
        message_domain_to_dto(
            Message(role="user", content="handoff", is_handoff=True),
            session.id,
            idx=0,
        ),
    )

    handoffs = await message_store.get_handoff_messages(session.id, limit=1)
    assert len(handoffs) == 1
    assert handoffs[0].is_handoff is True
    assert handoffs[0].content == "handoff"
