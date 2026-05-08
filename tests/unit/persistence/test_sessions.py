"""Tests for session archival auto-save to memory store."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, SessionState
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore


@pytest.fixture
async def store_with_memory(tmp_path):
    """Create a SessionStore and MemoryStore with a temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()

    memory_store = MemoryStore(db)
    await memory_store.create_table()

    summarizer = MagicMock()
    store = SessionStore(db, memory_store=memory_store, session_summarizer=summarizer)

    yield store, memory_store, summarizer
    await db.close()


class TestSessionAutoSave:
    @pytest.mark.asyncio
    async def test_archive_session_with_messages_creates_memory(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session.id, Message(role="user", content="Find me a job")
        )
        await store.append_message(
            session.id, Message(role="assistant", content="Here are some roles...")
        )

        summarizer.summarize = AsyncMock(
            return_value="User is looking for software engineering roles."
        )

        await store.archive_session(session.id)

        memories = await memory_store.list_memories()
        assert len(memories) == 1
        assert memories[0].content == "User is looking for software engineering roles."
        assert "job-search" in memories[0].tags
        assert memories[0].session_id == session.id
        assert memories[0].platform == "cli"
        assert memories[0].platform_user == "testuser"

    @pytest.mark.asyncio
    async def test_archive_session_with_no_messages_no_memory(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session = await store.get_or_create_session("cli", "testuser")
        summarizer.summarize = AsyncMock(return_value="")

        await store.archive_session(session.id)

        memories = await memory_store.list_memories()
        assert len(memories) == 0

    @pytest.mark.asyncio
    async def test_archive_session_summarizer_failure_no_crash(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session.id, Message(role="user", content="Hello"))
        await store.append_message(
            session.id, Message(role="assistant", content="Hi")
        )

        summarizer.summarize = AsyncMock(side_effect=Exception("Inference failed"))

        # Should not raise
        await store.archive_session(session.id)

        memories = await memory_store.list_memories()
        assert len(memories) == 0

    @pytest.mark.asyncio
    async def test_create_session_with_archive_creates_memory(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session1 = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session1.id, Message(role="user", content="What's the weather?")
        )
        await store.append_message(
            session1.id, Message(role="assistant", content="It's sunny.")
        )

        summarizer.summarize = AsyncMock(return_value="User asked about weather.")

        session2 = await store.create_session(
            "cli", "testuser", archive_previous=session1
        )

        memories = await memory_store.list_memories()
        assert len(memories) == 1
        assert memories[0].content == "User asked about weather."
        assert "weather" in memories[0].tags
        assert memories[0].session_id == session1.id

        # New session is active
        assert session2.state == SessionState.ACTIVE
        fetched1 = await store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_tag_inference_general(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session.id, Message(role="user", content="Hello"))
        await store.append_message(
            session.id, Message(role="assistant", content="Hi")
        )

        summarizer.summarize = AsyncMock(
            return_value="Random chat about nothing specific."
        )

        await store.archive_session(session.id)

        memories = await memory_store.list_memories()
        assert len(memories) == 1
        assert "general" in memories[0].tags

    @pytest.mark.asyncio
    async def test_tag_inference_memory_config(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session.id, Message(role="user", content="Remember my name")
        )
        await store.append_message(
            session.id, Message(role="assistant", content="Got it.")
        )

        summarizer.summarize = AsyncMock(
            return_value="User wants me to remember their preferences."
        )

        await store.archive_session(session.id)

        memories = await memory_store.list_memories()
        assert len(memories) == 1
        assert "memory-config" in memories[0].tags

    @pytest.mark.asyncio
    async def test_end_session_delegates_and_auto_saves(self, store_with_memory):
        store, memory_store, summarizer = store_with_memory

        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session.id, Message(role="user", content="Hello"))
        await store.append_message(
            session.id, Message(role="assistant", content="Hi")
        )

        summarizer.summarize = AsyncMock(return_value="A greeting.")

        await store.end_session(session.id, "test cleanup")

        memories = await memory_store.list_memories()
        assert len(memories) == 1
        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED
