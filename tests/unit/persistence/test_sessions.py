"""Tests for session persistence."""

import json

import pytest

from hestia.core.types import ChatResponse, Message, SessionState
from hestia.memory.compaction_summarizer import SessionCompactionSummarizer
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


class FakeInferenceClient:
    """Inference client that returns a deterministic compaction JSON summary."""

    model_name = "fake-model"

    def __init__(self, summary_json: dict | None = None):
        self._summary_json = summary_json or {
            "goal": "Plan a trip",
            "criteria": "Prefer warm weather",
            "progress_done": "Discussed dates",
            "pending": "Book flights",
            "key_findings": "User likes direct flights",
            "artifact_paths": ["art_abc123def4"],
            "summary": "Planning a warm-weather trip; direct flights preferred.",
        }

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools):
        return sum(10 + len(m.content) // 4 for m in messages) + 50 * len(tools)

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        return ChatResponse(
            content=json.dumps(self._summary_json),
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


def make_archive_store(store, message_store, memory_store, inference=None):
    """Build a SessionStore wired for archive-time memory extraction."""
    if inference is None:
        inference = FakeInferenceClient()
    summarizer = SessionCompactionSummarizer(
        inference=inference,
        memory_store=memory_store,
        min_messages=4,
    )
    return SessionStore(
        store._db,
        event_bus=store._event_bus,
        message_store=message_store,
        memory_store=memory_store,
        archive_summarizer=summarizer,
    )


async def populate_session(message_store, session_id, turns=4):
    """Add enough user/assistant turns to pass the trivial-session gate."""
    for i in range(turns):
        await message_store.append_message(
            session_id,
            Message(role="user", content=f"User message {i}"),
        )
        await message_store.append_message(
            session_id,
            Message(role="assistant", content=f"Assistant reply {i}"),
        )


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
    async def test_archive_session_saves_structured_facts(
        self, store, message_store, memory_store
    ):
        store_with_memory = make_archive_store(store, message_store, memory_store)
        session = await store_with_memory.get_or_create_session("cli", "testuser")
        await populate_session(message_store, session.id)

        summary = await store_with_memory.archive_session(session.id)

        assert summary == "Planning a warm-weather trip; direct flights preferred."
        memories = await memory_store.list_memories(platform="cli", platform_user="testuser")
        assert len(memories) == 1
        memory = memories[0]
        assert "compaction" in memory.tags
        assert "task-state" in memory.tags
        assert "Goal: Plan a trip" in memory.content
        assert "Findings: User likes direct flights" in memory.content
        assert memory.session_id == session.id

    @pytest.mark.asyncio
    async def test_archive_session_skips_trivial_session(
        self, store, message_store, memory_store
    ):
        store_with_memory = make_archive_store(store, message_store, memory_store)
        session = await store_with_memory.get_or_create_session("cli", "testuser")
        # Only two messages, below the default min_messages threshold.
        await message_store.append_message(
            session.id, Message(role="user", content="hello")
        )
        await message_store.append_message(
            session.id, Message(role="assistant", content="hi")
        )

        summary = await store_with_memory.archive_session(session.id)

        assert summary is None
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
        await populate_session(message_store, session.id)
        summary = await store_with_memory.archive_session(session.id)

        assert summary is None
        memories = await memory_store.list_memories(platform="cli", platform_user="testuser")
        assert memories == []

    @pytest.mark.asyncio
    async def test_archive_session_dedups_existing_memory(
        self, store, message_store, memory_store
    ):
        store_with_memory = make_archive_store(store, message_store, memory_store)
        session = await store_with_memory.get_or_create_session("cli", "testuser")
        await populate_session(message_store, session.id)

        # Pre-seed the exact memory the archive summarizer will produce.
        expected_memory = (
            "Goal: Plan a trip\n"
            "Criteria: Prefer warm weather\n"
            "Done: Discussed dates\n"
            "Pending: Book flights\n"
            "Findings: User likes direct flights\n"
            "Artifacts: art_abc123def4"
        )
        await memory_store.save(
            content=expected_memory,
            tags=["compaction", "task-state"],
            session_id=session.id,
            platform=session.platform,
            platform_user=session.platform_user,
        )

        await store_with_memory.archive_session(session.id)

        memories = await memory_store.list_memories(platform="cli", platform_user="testuser")
        assert len(memories) == 1

    @pytest.mark.asyncio
    async def test_archive_session_twice_does_not_duplicate(
        self, store, message_store, memory_store
    ):
        store_with_memory = make_archive_store(store, message_store, memory_store)
        session = await store_with_memory.get_or_create_session("cli", "testuser")
        await populate_session(message_store, session.id)

        await store_with_memory.archive_session(session.id)
        await store_with_memory.archive_session(session.id)

        memories = await memory_store.list_memories(platform="cli", platform_user="testuser")
        assert len(memories) == 1
