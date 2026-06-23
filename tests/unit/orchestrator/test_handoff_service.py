"""Unit tests for HandoffService."""

import json

import pytest

from hestia.core.types import ChatResponse, Message
from hestia.memory.compaction_summarizer import SessionCompactionSummarizer
from hestia.memory.store import MemoryStore
from hestia.orchestrator.handoff_service import HandoffService
from hestia.orchestrator.mappers import message_domain_to_dto
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


class FakeInferenceClient:
    """Inference client that returns a deterministic compaction JSON summary."""

    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools):
        return sum(10 + len(m.content) // 4 for m in messages) + 50 * len(tools)

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        return ChatResponse(
            content=json.dumps(
                {
                    "goal": "Plan a trip",
                    "criteria": "Prefer warm weather",
                    "progress_done": "Discussed dates",
                    "pending": "Book flights",
                    "key_findings": "User likes direct flights",
                    "artifact_paths": [],
                    "summary": "Planning a warm-weather trip.",
                }
            ),
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        pass


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
async def memory_store(db):
    store = MemoryStore(db)
    await store.create_table()
    return store


@pytest.fixture
async def message_store(db):
    return MessageStore(db)


@pytest.fixture
async def handoff_service(session_store, message_store):
    return HandoffService(session_store, message_store)


@pytest.fixture
async def handoff_service_with_summarizer(session_store, message_store, memory_store):
    summarizer = SessionCompactionSummarizer(
        inference=FakeInferenceClient(),
        memory_store=memory_store,
        min_messages=4,
    )
    store = SessionStore(
        session_store._db,
        message_store=message_store,
        memory_store=memory_store,
        archive_summarizer=summarizer,
    )
    return HandoffService(store, message_store)


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
async def test_generate_handoff_summary_reuses_archive_summary(
    message_store, handoff_service_with_summarizer
):
    """A single archive produces one summary reused for the handoff message."""
    session = await handoff_service_with_summarizer._session_store.get_or_create_session(
        "cli", "testuser"
    )
    for i in range(4):
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="user", content=f"User {i}"), session.id, idx=0
            ),
        )
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="assistant", content=f"Reply {i}"), session.id, idx=0
            ),
        )

    await handoff_service_with_summarizer.generate_handoff_summary(session.id)

    archived = await handoff_service_with_summarizer._session_store.get_session(session.id)
    assert archived.state.value == "archived"

    handoffs = await message_store.get_handoff_messages(session.id)
    assert len(handoffs) == 1
    assert "Planning a warm-weather trip." in handoffs[0].content

    memories = await handoff_service_with_summarizer._session_store._memory_store.list_memories(
        platform="cli", platform_user="testuser"
    )
    assert len(memories) == 1
    assert "Goal: Plan a trip" in memories[0].content


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
