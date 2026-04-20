"""Tests for memory user scoping (L45b)."""

from __future__ import annotations

import pytest

from hestia.memory.store import Memory, MemoryStore
from hestia.persistence.db import Database
from hestia.runtime_context import current_platform, current_platform_user
from hestia.tools.builtin.memory_tools import (
    make_delete_memory_tool,
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
)


class TestMemoryUserScope:
    @pytest.fixture
    async def memory_store(self, tmp_path):
        """Create a MemoryStore with a fresh in-memory database."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_save_includes_user_scope(self, memory_store):
        """Saving a memory with explicit platform/user stores both."""
        mem = await memory_store.save(
            content="User-scoped note",
            tags=["test"],
            platform="cli",
            platform_user="alice",
        )
        assert mem.platform == "cli"
        assert mem.platform_user == "alice"

    @pytest.mark.asyncio
    async def test_search_filters_by_user(self, memory_store):
        """Search only returns memories for the scoped user."""
        await memory_store.save(content="Alice's secret", platform="cli", platform_user="alice")
        await memory_store.save(content="Bob's secret", platform="cli", platform_user="bob")

        alice_results = await memory_store.search("secret", platform="cli", platform_user="alice")
        assert len(alice_results) == 1
        assert "Alice" in alice_results[0].content

        bob_results = await memory_store.search("secret", platform="cli", platform_user="bob")
        assert len(bob_results) == 1
        assert "Bob" in bob_results[0].content

    @pytest.mark.asyncio
    async def test_list_memories_filters_by_user(self, memory_store):
        """list_memories only returns memories for the scoped user."""
        await memory_store.save(content="Alice note", platform="matrix", platform_user="alice")
        await memory_store.save(content="Bob note", platform="matrix", platform_user="bob")

        alice_memories = await memory_store.list_memories(platform="matrix", platform_user="alice")
        assert len(alice_memories) == 1
        assert alice_memories[0].content == "Alice note"

    @pytest.mark.asyncio
    async def test_delete_scoped_to_user(self, memory_store):
        """Delete only removes memories belonging to the scoped user."""
        mem = await memory_store.save(content="Alice note", platform="cli", platform_user="alice")

        # Bob tries to delete Alice's memory
        deleted = await memory_store.delete(mem.id, platform="cli", platform_user="bob")
        assert deleted is False

        # Alice deletes her own memory
        deleted = await memory_store.delete(mem.id, platform="cli", platform_user="alice")
        assert deleted is True

    @pytest.mark.asyncio
    async def test_count_scoped_to_user(self, memory_store):
        """Count only counts memories for the scoped user."""
        await memory_store.save(content="Alice 1", platform="cli", platform_user="alice")
        await memory_store.save(content="Alice 2", platform="cli", platform_user="alice")
        await memory_store.save(content="Bob 1", platform="cli", platform_user="bob")

        assert await memory_store.count(platform="cli", platform_user="alice") == 2
        assert await memory_store.count(platform="cli", platform_user="bob") == 1

    @pytest.mark.asyncio
    async def test_cross_user_access_blocked(self, memory_store):
        """Users cannot see each other's memories."""
        await memory_store.save(content="Alice private", platform="cli", platform_user="alice")

        # Bob searches for Alice's content
        results = await memory_store.search("private", platform="cli", platform_user="bob")
        assert results == []

        # Bob lists memories
        memories = await memory_store.list_memories(platform="cli", platform_user="bob")
        assert memories == []

    @pytest.mark.asyncio
    async def test_search_reads_identity_from_contextvar(self, memory_store):
        """Search falls back to runtime ContextVars for user identity."""
        await memory_store.save(content="Context note", platform="matrix", platform_user="eve")

        token_p = current_platform.set("matrix")
        token_u = current_platform_user.set("eve")
        try:
            results = await memory_store.search("Context")
            assert len(results) == 1
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)

    @pytest.mark.asyncio
    async def test_save_reads_identity_from_contextvar(self, memory_store):
        """Save falls back to runtime ContextVars for user identity."""
        token_p = current_platform.set("matrix")
        token_u = current_platform_user.set("eve")
        try:
            mem = await memory_store.save(content="Eve note")
            assert mem.platform == "matrix"
            assert mem.platform_user == "eve"
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)


class TestMemoryToolsUserScope:
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
        delete_tool = make_delete_memory_tool(store)

        yield store, search_tool, save_tool, list_tool, delete_tool
        await db.close()

    @pytest.mark.asyncio
    async def test_save_memory_tool_uses_contextvar_identity(self, tools):
        """save_memory records platform/platform_user from runtime ContextVars."""
        store, _, save_tool, _, _ = tools

        token_p = current_platform.set("cli")
        token_u = current_platform_user.set("dylan")
        try:
            result = await save_tool("Scoped memory", tags="test")
            assert "Saved memory" in result

            memories = await store.list_memories(platform="cli", platform_user="dylan")
            assert len(memories) == 1
            assert memories[0].platform == "cli"
            assert memories[0].platform_user == "dylan"
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)

    @pytest.mark.asyncio
    async def test_search_memory_tool_uses_contextvar_identity(self, tools):
        """search_memory only finds memories for the current ContextVar user."""
        store, search_tool, save_tool, _, _ = tools

        # Save as Alice
        token_p = current_platform.set("matrix")
        token_u = current_platform_user.set("alice")
        try:
            await save_tool("Alice's note", tags="test")
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)

        # Save as Bob
        token_p = current_platform.set("matrix")
        token_u = current_platform_user.set("bob")
        try:
            await save_tool("Bob's note", tags="test")
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)

        # Search as Alice
        token_p = current_platform.set("matrix")
        token_u = current_platform_user.set("alice")
        try:
            result = await search_tool("note")
            assert "Alice" in result
            assert "Bob" not in result
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)

    @pytest.mark.asyncio
    async def test_list_memories_tool_uses_contextvar_identity(self, tools):
        """list_memories only returns memories for the current ContextVar user."""
        store, _, save_tool, list_tool, _ = tools

        token_p = current_platform.set("cli")
        token_u = current_platform_user.set("user1")
        try:
            await save_tool("User1 note")
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)

        token_p = current_platform.set("cli")
        token_u = current_platform_user.set("user2")
        try:
            result = await list_tool()
            assert "No memories found" in result
        finally:
            current_platform.reset(token_p)
            current_platform_user.reset(token_u)


class TestMemoryLikeFallback:
    @pytest.fixture
    async def like_store(self, tmp_path):
        """Create a MemoryStore that simulates FTS5 absence."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        # Force FTS5 unavailable before create_table
        store._fts5_available = False
        await store.create_table()
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_like_fallback_search(self, like_store):
        """Search works via LIKE when FTS5 is unavailable."""
        await like_store.save(content="Python programming", platform="cli", platform_user="test")
        await like_store.save(content="Python snake", platform="cli", platform_user="test")

        results = await like_store.search("programming", platform="cli", platform_user="test")
        assert len(results) == 1
        assert "programming" in results[0].content

    @pytest.mark.asyncio
    async def test_like_fallback_list_by_tag(self, like_store):
        """Tag filtering works via LIKE when FTS5 is unavailable."""
        await like_store.save(content="Work task", tags=["work"], platform="cli", platform_user="test")
        await like_store.save(content="Personal task", tags=["personal"], platform="cli", platform_user="test")

        results = await like_store.list_memories(tag="work", platform="cli", platform_user="test")
        assert len(results) == 1
        assert "Work task" in results[0].content

    @pytest.mark.asyncio
    async def test_like_fallback_no_false_tag_match(self, like_store):
        """LIKE fallback does not match partial tag tokens."""
        await like_store.save(content="Documentation", tags=["docs"], platform="cli", platform_user="test")
        await like_store.save(content="Doctor appointment", tags=["doctor"], platform="cli", platform_user="test")

        results = await like_store.list_memories(tag="doc", platform="cli", platform_user="test")
        assert len(results) == 0

        results = await like_store.list_memories(tag="docs", platform="cli", platform_user="test")
        assert len(results) == 1
        assert "Documentation" in results[0].content


class TestMemoryFTS5Migration:
    @pytest.mark.asyncio
    async def test_old_schema_migration(self, tmp_path):
        """Old memory table without platform/platform_user is migrated."""
        db_path = tmp_path / "test_migration.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()

        # Create old-schema table manually
        await db.execute(
            sa.text(
                "CREATE VIRTUAL TABLE memory USING fts5("
                "id UNINDEXED, content, tags, session_id UNINDEXED, created_at UNINDEXED)"
            )
        )
        await db.execute(
            sa.text(
                "INSERT INTO memory (id, content, tags, session_id, created_at) "
                "VALUES ('mem_old', 'Legacy memory', 'legacy', 'sess_old', '2026-01-01T00:00:00')"
            )
        )

        store = MemoryStore(db)
        await store.create_table()

        # Verify old data is preserved with NULL platform/platform_user
        results = await store.search("Legacy")
        assert len(results) == 1
        assert results[0].platform is None
        assert results[0].platform_user is None

        # Verify new saves include platform/platform_user
        mem = await store.save(content="New memory", platform="cli", platform_user="test")
        assert mem.platform == "cli"
        assert mem.platform_user == "test"

        await db.close()


import sqlalchemy as sa
