"""Unit tests for HandoffService."""

import pytest

from hestia.core.types import Message
from hestia.orchestrator.handoff_service import HandoffService
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


@pytest.fixture
async def handoff_service(session_store, message_store):
    return HandoffService(session_store, message_store)


@pytest.mark.asyncio
async def test_generate_handoff_summary_creates_handoff_message(
    session_store, message_store, handoff_service
):
    """generate_handoff_summary archives the session and writes an is_handoff message."""
    session = await session_store.get_or_create_session("cli", "testuser")
    await message_store.append_message(
        session.id,
        message_domain_to_dto(
            Message(role="user", content="Hello"), session.id, idx=0
        ),
    )

    await handoff_service.generate_handoff_summary(session.id, summary="Prior context")

    archived = await session_store.get_session(session.id)
    assert archived.state.value == "archived"

    handoffs = await message_store.get_handoff_messages(session.id)
    assert len(handoffs) == 1
    assert handoffs[0].is_handoff is True
    assert "[Previous session context]" in handoffs[0].content
    assert "Prior context" in handoffs[0].content


@pytest.mark.asyncio
async def test_get_recent_handoffs_returns_latest(
    session_store, message_store, handoff_service
):
    """get_recent_handoffs returns the most recent handoff for an identity."""
    session1 = await session_store.get_or_create_session("cli", "testuser")
    await handoff_service.generate_handoff_summary(session1.id, summary="First")

    session2 = await session_store.get_or_create_session("cli", "testuser")
    await handoff_service.generate_handoff_summary(session2.id, summary="Second")

    handoffs = await handoff_service.get_recent_handoffs("cli", "testuser")
    assert len(handoffs) == 1
    assert "Second" in handoffs[0]["summary"]


@pytest.mark.asyncio
async def test_get_or_create_session_with_handoff_injects_for_new_session(
    session_store, message_store, handoff_service
):
    """A brand-new session gets a synthetic handoff message when one exists."""
    old = await session_store.get_or_create_session("cli", "testuser")
    await message_store.append_message(
        old.id,
        message_domain_to_dto(Message(role="user", content="Old"), old.id, idx=0),
    )
    await handoff_service.generate_handoff_summary(old.id, summary="Old context")

    new_session = await handoff_service.get_or_create_session_with_handoff(
        "cli", "testuser"
    )
    messages = await message_store.get_messages(new_session.id)
    assert len(messages) == 1
    assert messages[0].is_handoff is True
    assert "Old context" in messages[0].content


@pytest.mark.asyncio
async def test_get_or_create_session_with_handoff_skips_existing_messages(
    session_store, message_store, handoff_service
):
    """An existing active session with messages does not get a handoff injection."""
    old = await session_store.get_or_create_session("cli", "testuser")
    await message_store.append_message(
        old.id,
        message_domain_to_dto(Message(role="user", content="Old"), old.id, idx=0),
    )
    await handoff_service.generate_handoff_summary(old.id, summary="Old context")

    active = await session_store.get_or_create_session("cli", "testuser")
    await message_store.append_message(
        active.id,
        message_domain_to_dto(Message(role="user", content="First"), active.id, idx=0),
    )

    result = await handoff_service.get_or_create_session_with_handoff(
        "cli", "testuser"
    )
    messages = await message_store.get_messages(result.id)
    assert len(messages) == 1
    assert messages[0].content == "First"
