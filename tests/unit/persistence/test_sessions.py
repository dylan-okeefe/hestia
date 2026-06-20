"""Tests for session persistence."""

from unittest.mock import AsyncMock

import pytest

from hestia.core.types import Message, SessionState
from hestia.memory.session_summarizer import SessionSummarizer
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with a temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()

    store = SessionStore(db)

    yield store
    await db.close()


@pytest.fixture
async def message_store(store):
    """Create a MessageStore bound to the same database."""
    return MessageStore(store._db)


@pytest.fixture
async def memory_store(store):
    """Create a MemoryStore bound to the same database."""
    ms = MemoryStore(store._db)
    await ms.create_table()
    return ms


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_archive_session(self, store):
        session = await store.get_or_create_session("cli", "testuser")

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_create_session_with_archive(self, store):
        session1 = await store.get_or_create_session("cli", "testuser")

        session2 = await store.create_session(
            "cli", "testuser", archive_previous=session1
        )

        fetched1 = await store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

        # New session is active
        assert session2.state == SessionState.ACTIVE

    @pytest.mark.asyncio
    async def test_end_session_archives(self, store):
        session = await store.get_or_create_session("cli", "testuser")

        await store.end_session(session.id, "test cleanup")

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_get_active_session_returns_active_or_none(self, store):
        session = await store.get_or_create_session("cli", "testuser")

        active = await store.get_active_session("cli", "testuser")
        assert active is not None
        assert active.id == session.id

        await store.archive_session(session.id)

        active_after_archive = await store.get_active_session("cli", "testuser")
        assert active_after_archive is None

        # Other users are unaffected
        other = await store.get_or_create_session("cli", "otheruser")
        other_active = await store.get_active_session("cli", "otheruser")
        assert other_active is not None
        assert other_active.id == other.id

    @pytest.mark.asyncio
    async def test_archive_session_bumps_last_active_via_message_store(
        self, store, message_store
    ):
        session = await store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            session.id,
            Message(role="user", content="hello"),
        )

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_archive_session_auto_saves_summary_to_memory(
        self, store, message_store, memory_store
    ):
        summarizer = SessionSummarizer(inference=AsyncMock())
        summarizer._inference.chat = AsyncMock(
            return_value=AsyncMock(
                content="User asked about the weather and prefers Celsius.",
            )
        )
        store_with_memory = SessionStore(
            store._db,
            event_bus=store._event_bus,
            message_store=message_store,
            memory_store=memory_store,
            session_summarizer=summarizer,
        )

        session = await store_with_memory.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            session.id,
            Message(role="user", content="What's the weather like today?"),
        )
        await message_store.append_message(
            session.id,
            Message(role="assistant", content="It's sunny and 20C."),
        )

        await store_with_memory.archive_session(session.id)

        memories = await memory_store.search("weather", platform="cli", platform_user="testuser")
        assert len(memories) == 1
        assert "session-summary" in memories[0].tags
        assert "weather" in memories[0].tags
        assert memories[0].session_id == session.id

    @pytest.mark.asyncio
    async def test_archive_session_without_messages_does_not_create_memory(
        self, store, message_store, memory_store
    ):
        summarizer = SessionSummarizer(inference=AsyncMock())
        summarizer._inference.chat = AsyncMock(return_value=AsyncMock(content=""))
        store_with_memory = SessionStore(
            store._db,
            event_bus=store._event_bus,
            message_store=message_store,
            memory_store=memory_store,
            session_summarizer=summarizer,
        )

        session = await store_with_memory.get_or_create_session("cli", "testuser")
        await store_with_memory.archive_session(session.id)

        memories = await memory_store.list_memories(platform="cli", platform_user="testuser")
        assert memories == []

    @pytest.mark.asyncio
    async def test_archive_session_without_summarizer_does_not_create_memory(
        self, store, message_store, memory_store
    ):
        store_with_memory = SessionStore(
            store._db,
            event_bus=store._event_bus,
            message_store=message_store,
            memory_store=memory_store,
        )

        session = await store_with_memory.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            session.id,
            Message(role="user", content="hello"),
        )
        await store_with_memory.archive_session(session.id)

        memories = await memory_store.list_memories(platform="cli", platform_user="testuser")
        assert memories == []
