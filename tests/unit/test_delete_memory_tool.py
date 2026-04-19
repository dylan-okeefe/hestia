"""Regression tests for delete_memory tool (§2 L28)."""

from __future__ import annotations

import pytest

from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.tools.builtin.memory_tools import make_delete_memory_tool, make_list_memories_tool


class TestDeleteMemoryTool:
    @pytest.fixture
    async def tools(self, tmp_path):
        """Create delete_memory tool bound to a fresh MemoryStore."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()

        delete_tool = make_delete_memory_tool(store)
        list_tool = make_list_memories_tool(store)

        yield store, delete_tool, list_tool
        await db.close()

    @pytest.mark.asyncio
    async def test_delete_existing_memory(self, tools):
        """save → delete by id → list → assert empty."""
        store, delete_tool, list_tool = tools
        mem = await store.save(content="To be deleted", tags=["test"])

        result = await delete_tool(mem.id)
        assert "Deleted memory" in result
        assert mem.id in result

        list_result = await list_tool()
        assert "No memories found" in list_result

    @pytest.mark.asyncio
    async def test_delete_unknown_id_returns_friendly_message(self, tools):
        """delete unknown id → friendly message."""
        _, delete_tool, _ = tools
        result = await delete_tool("nonexistent-id")
        assert "No memory with id nonexistent-id" in result

    @pytest.mark.asyncio
    async def test_tool_has_proper_metadata(self, tools):
        """delete_memory has proper tool metadata."""
        _, delete_tool, _ = tools
        assert hasattr(delete_tool, "__hestia_tool__")
        assert delete_tool.__hestia_tool__.name == "delete_memory"
        assert delete_tool.__hestia_tool__.requires_confirmation is True
