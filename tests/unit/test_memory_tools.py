"""Unit tests for memory tools."""

import pytest

from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.tools.builtin.memory_tools import (
    current_session_id,
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
)


class TestSearchMemoryTool:
    @pytest.fixture
    async def tools(self, tmp_path):
        """Create memory tools bound to a fresh MemoryStore."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()

        search_tool = make_search_memory_tool(store)
        save_tool = make_save_memory_tool(store)
        list_tool = make_list_memories_tool(store)

        yield store, search_tool, save_tool, list_tool
        await db.close()

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self, tools):
        """search_memory returns formatted results with IDs and dates."""
        store, search_tool, save_tool, _ = tools
        await store.save("The meeting is at 3pm", tags=["meetings"])
        result = await search_tool("meeting")
        assert "3pm" in result
        assert "meetings" in result
        assert "mem_" in result  # Memory ID format

    @pytest.mark.asyncio
    async def test_search_no_results_message(self, tools):
        """search_memory returns helpful message when no results."""
        _, search_tool, _, _ = tools
        result = await search_tool("nonexistent")
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_search_with_limit(self, tools):
        """search_memory respects limit parameter."""
        store, search_tool, _, _ = tools
        for i in range(5):
            await store.save(f"Memory {i}")
        result = await search_tool("Memory", limit=2)
        # Should have 2 results (format: [id] (date) content)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_save_returns_confirmation(self, tools):
        """save_memory returns confirmation with ID and preview."""
        _, _, save_tool, _ = tools
        result = await save_tool("Remember to buy milk", tags="shopping groceries")
        assert "Saved memory" in result
        assert "mem_" in result
        assert "buy milk" in result

    @pytest.mark.asyncio
    async def test_save_long_content_truncates(self, tools):
        """save_memory truncates long content in confirmation."""
        _, _, save_tool, _ = tools
        long_content = "x" * 100
        result = await save_tool(long_content)
        assert "..." in result
        assert len(result) < 150  # Should be truncated

    @pytest.mark.asyncio
    async def test_list_memories_returns_formatted(self, tools):
        """list_memories returns formatted list."""
        store, _, _, list_tool = tools
        await store.save("First memory")
        await store.save("Second memory", tags=["important"])
        result = await list_tool()
        assert "First memory" in result
        assert "Second memory" in result
        assert "important" in result

    @pytest.mark.asyncio
    async def test_list_memories_empty(self, tools):
        """list_memories returns helpful message when empty."""
        _, _, _, list_tool = tools
        result = await list_tool()
        assert "No memories found" in result

    @pytest.mark.asyncio
    async def test_list_memories_filter_by_tag(self, tools):
        """list_memories can filter by tag."""
        store, _, _, list_tool = tools
        await store.save("Important thing", tags=["important"])
        await store.save("Trivial thing", tags=["trivial"])

        result = await list_tool(tag="important")
        assert "Important thing" in result
        assert "Trivial thing" not in result

    @pytest.mark.asyncio
    async def test_list_memories_no_results_with_tag_filter(self, tools):
        """list_memories shows tag filter info when no matches."""
        _, _, _, list_tool = tools
        result = await list_tool(tag="nonexistent")
        assert "No memories found" in result
        assert "filtered by tag" in result

    @pytest.mark.asyncio
    async def test_list_memories_with_limit(self, tools):
        """list_memories respects limit parameter."""
        store, _, _, list_tool = tools
        for i in range(10):
            await store.save(f"Memory {i}")

        result = await list_tool(limit=3)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_tools_are_properly_decorated(self, tools):
        """Memory tools have proper tool metadata."""
        _, search_tool, save_tool, list_tool = tools

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
        store, _, save_tool, _ = tools

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
        store, _, save_tool, _ = tools

        # Ensure no session context is set
        assert current_session_id.get() is None

        result = await save_tool("Memory without session", tags="test")
        assert "Saved memory" in result

        # Verify memory was saved with None session_id
        memories = await store.list_memories()
        assert len(memories) == 1
        assert memories[0].session_id is None
