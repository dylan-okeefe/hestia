"""Unit tests for memory tools."""

from datetime import UTC

import pytest

from hestia.memory.epochs import MemoryEpochCompiler
from hestia.memory.store import MemoryStore
from hestia.memory.topics import TopicStore
from hestia.persistence.db import Database
from hestia.runtime_context import current_platform, current_platform_user, current_session_id
from hestia.tools.builtin.memory_tools import (
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
)


class TestSearchMemoryTool:
    @pytest.fixture
    async def tools(self, tmp_path):
        """Create memory tools bound to a fresh MemoryStore and TopicStore."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()
        topic_store = TopicStore(db)

        search_tool = make_search_memory_tool(store)
        save_tool = make_save_memory_tool(store, topic_store)
        list_tool = make_list_memories_tool(store)

        platform_token = current_platform.set("test")
        platform_user_token = current_platform_user.set("test_user")

        yield store, topic_store, search_tool, save_tool, list_tool

        current_platform.reset(platform_token)
        current_platform_user.reset(platform_user_token)
        await db.close()

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self, tools):
        """search_memory returns formatted results with IDs and dates."""
        store, topic_store, search_tool, save_tool, _ = tools
        await store.save("The meeting is at 3pm", tags=["meetings"])
        result = await search_tool("meeting")
        assert "3pm" in result
        assert "meetings" in result
        assert "mem_" in result  # Memory ID format

    @pytest.mark.asyncio
    async def test_search_no_results_message(self, tools):
        """search_memory returns helpful message when no results."""
        _, topic_store, search_tool, _, _ = tools
        result = await search_tool("nonexistent")
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_search_with_limit(self, tools):
        """search_memory respects limit parameter."""
        store, topic_store, search_tool, _, _ = tools
        for i in range(5):
            await store.save(f"Memory {i}")
        result = await search_tool("Memory", limit=2)
        # Should have 2 results (format: [id] (date) content)
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_save_returns_confirmation(self, tools):
        """save_memory returns confirmation with ID and preview."""
        _, _, topic_store, save_tool, _ = tools
        result = await save_tool("Remember to buy milk", tags="shopping groceries")
        assert "Saved memory" in result
        assert "mem_" in result
        assert "buy milk" in result

    @pytest.mark.asyncio
    async def test_save_long_content_truncates(self, tools):
        """save_memory truncates long content in confirmation."""
        _, _, topic_store, save_tool, _ = tools
        long_content = "x" * 100
        result = await save_tool(long_content)
        assert "..." in result
        assert len(result) < 150  # Should be truncated

    @pytest.mark.asyncio
    async def test_list_memories_returns_formatted(self, tools):
        """list_memories returns formatted list."""
        store, topic_store, _, _, list_tool = tools
        await store.save("First memory")
        await store.save("Second memory", tags=["important"])
        result = await list_tool()
        assert "First memory" in result
        assert "Second memory" in result
        assert "important" in result

    @pytest.mark.asyncio
    async def test_list_memories_empty(self, tools):
        """list_memories returns helpful message when empty."""
        _, _, topic_store, _, list_tool = tools
        result = await list_tool()
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_list_memories_filter_by_tag(self, tools):
        """list_memories can filter by tag."""
        store, topic_store, _, _, list_tool = tools
        await store.save("Important thing", tags=["important"])
        await store.save("Trivial thing", tags=["trivial"])

        result = await list_tool(tag="important")
        assert "Important thing" in result
        assert "Trivial thing" not in result

    @pytest.mark.asyncio
    async def test_list_memories_no_results_with_tag_filter(self, tools):
        """list_memories shows tag filter info when no matches."""
        _, _, topic_store, _, list_tool = tools
        result = await list_tool(tag="nonexistent")
        assert "No memories found" in result
        assert "filtered by tag" in result

    @pytest.mark.asyncio
    async def test_list_memories_with_limit(self, tools):
        """list_memories respects limit parameter."""
        store, topic_store, _, _, list_tool = tools
        for i in range(10):
            await store.save(f"Memory {i}")

        result = await list_tool(limit=3)
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_tools_are_properly_decorated(self, tools):
        """Memory tools have proper tool metadata."""
        _, topic_store, search_tool, save_tool, list_tool = tools

        # Check that they have the tool metadata
        assert hasattr(search_tool, "__hestia_tool__")
        assert hasattr(save_tool, "__hestia_tool__")
        assert hasattr(list_tool, "__hestia_tool__")

        # Check names
        assert search_tool.__hestia_tool__.name == "search_memory"
        assert save_tool.__hestia_tool__.name == "save_memory"
        assert list_tool.__hestia_tool__.name == "list_memories"

        # Check tags
        assert "memory" in search_tool.__hestia_tool__.tags
        assert "memory" in save_tool.__hestia_tool__.tags
        assert "memory" in list_tool.__hestia_tool__.tags

        # Check descriptions
        assert "Search" in search_tool.__hestia_tool__.public_description
        assert "Save" in save_tool.__hestia_tool__.public_description
        assert "List" in list_tool.__hestia_tool__.public_description

    @pytest.mark.asyncio
    async def test_save_memory_with_session_context(self, tools):
        """save_memory records session_id when contextvar is set."""
        store, topic_store, _, save_tool, _ = tools

        # Set the session context (as orchestrator would do)
        token = current_session_id.set("session_test_123")
        try:
            result = await save_tool("Memory with session", tags="test")
            assert "Saved memory" in result

            # Verify memory was saved with session_id
            memories = await store.list_memories()
            assert len(memories) == 1
            assert memories[0].session_id == "session_test_123"
        finally:
            current_session_id.reset(token)

    @pytest.mark.asyncio
    async def test_save_memory_without_session_context(self, tools):
        """save_memory works without session context (CLI usage)."""
        store, topic_store, _, save_tool, _ = tools

        # Ensure no session context is set
        assert current_session_id.get() is None

        result = await save_tool("Memory without session", tags="test")
        assert "Saved memory" in result

        # Verify memory was saved with None session_id
        memories = await store.list_memories()
        assert len(memories) == 1
        assert memories[0].session_id is None

    @pytest.mark.asyncio
    async def test_save_memory_rejects_junk_content(self, tools):
        """save_memory returns a graceful rejection message for junk content."""
        store, topic_store, _, save_tool, _ = tools
        result = await save_tool("<tool_call>search_memory</tool_call>")
        assert "rejected" in result.lower()
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_save_memory_accepts_clean_fact(self, tools):
        """save_memory stores clean prose facts normally."""
        store, topic_store, _, save_tool, _ = tools
        result = await save_tool("The user prefers remote roles.", tags="preference")
        assert "Saved memory" in result
        assert await store.count() == 1



class TestTopicScopedSaveMemoryTool:
    """Regression/integration tests for topic-scoped memory capture."""

    @pytest.fixture
    async def env(self, tmp_path):
        """Create stores, tools, and a session for topic-scoped tests."""
        from datetime import datetime

        from hestia.core.types import Session, SessionState, SessionTemperature

        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()
        topic_store = TopicStore(db)

        search_tool = make_search_memory_tool(store)
        save_tool = make_save_memory_tool(store, topic_store)
        list_tool = make_list_memories_tool(store)

        platform_token = current_platform.set("test")
        platform_user_token = current_platform_user.set("test_user")
        session_id = "session_abc"
        session_token = current_session_id.set(session_id)

        session = Session(
            id=session_id,
            platform="test",
            platform_user="test_user",
            started_at=datetime.now(UTC),
            last_active_at=datetime.now(UTC),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )

        compiler = MemoryEpochCompiler(store, max_tokens=500)

        yield store, topic_store, search_tool, save_tool, list_tool, session, compiler

        current_session_id.reset(session_token)
        current_platform.reset(platform_token)
        current_platform_user.reset(platform_user_token)
        await db.close()

    @pytest.mark.asyncio
    async def test_save_memory_no_topics_appears_in_epoch(self, env):
        """Regression guard: save_memory in a conversation with no explicit topics
        lands in the implicit topic and appears in the compiled epoch."""
        store, topic_store, _, save_tool, _, session, compiler = env

        result = await save_tool("Remember to review the design doc", tags="work")
        assert "Saved memory" in result

        topic_ids = await topic_store.get_conversation_topic_ids(session.id)
        assert len(topic_ids) == 1

        epoch = await compiler.compile(session, topic_ids=topic_ids)
        assert "Remember to review the design doc" in epoch.compiled_text

        memory = (await store.list_memories(limit=1))[0]
        assert memory.is_global is False

    @pytest.mark.asyncio
    async def test_save_memory_with_two_topics_associates_both(self, env):
        """A memory saved in a conversation subscribed to two topics is associated
        with both topics and appears in the epoch."""
        store, topic_store, _, save_tool, _, session, compiler = env

        topic_a = await topic_store.get_or_create_topic(
            session.platform, session.platform_user, "project-a"
        )
        topic_b = await topic_store.get_or_create_topic(
            session.platform, session.platform_user, "project-b"
        )
        await topic_store.subscribe_conversation(session.id, topic_a.id)
        await topic_store.subscribe_conversation(session.id, topic_b.id)

        result = await save_tool("Shared dependency on libfoo", tags="tech")
        assert "Saved memory" in result

        epoch = await compiler.compile(
            session,
            topic_ids=await topic_store.get_conversation_topic_ids(session.id),
        )
        assert "Shared dependency on libfoo" in epoch.compiled_text

        # Verify the memory row is not global and is reachable through both topics.
        memory = (await store.list_memories(limit=1))[0]
        assert memory.is_global is False

    @pytest.mark.asyncio
    async def test_save_memory_global_scope_is_always_loaded(self, env):
        """A global capture is is_global=1 and appears in the epoch even when the
        conversation has no topic subscriptions."""
        store, topic_store, _, save_tool, _, session, compiler = env

        result = await save_tool(
            "User lives in Pacific time", tags="preference", scope="global"
        )
        assert "Saved memory" in result

        epoch = await compiler.compile(session, topic_ids=[])
        assert "User lives in Pacific time" in epoch.compiled_text

        memory = (await store.list_memories(limit=1))[0]
        assert memory.is_global is True

        # Global memories should have no topic associations.
        assert await topic_store.get_conversation_topic_ids(session.id) == []

    @pytest.mark.asyncio
    async def test_save_memory_topic_scope_does_not_affect_other_conversation(self, env):
        """A topic-scoped memory in one conversation is not loaded into an unrelated
        conversation's epoch."""
        from datetime import datetime

        from hestia.core.types import Session, SessionState, SessionTemperature

        store, topic_store, _, save_tool, _, session, compiler = env

        await save_tool("Project alpha deadline is Friday", tags="work")

        other_session = Session(
            id="other_session",
            platform="test",
            platform_user="test_user",
            started_at=datetime.now(UTC),
            last_active_at=datetime.now(UTC),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.COLD,
        )
        epoch = await compiler.compile(
            other_session,
            topic_ids=await topic_store.get_conversation_topic_ids(other_session.id),
        )
        assert "Project alpha deadline is Friday" not in epoch.compiled_text
