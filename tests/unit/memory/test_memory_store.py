"""Unit tests for MemoryStore soft-delete and protected set (L226)."""

from __future__ import annotations

import pytest

from hestia.memory.store import MemoryStore
from hestia.memory.topics import TopicStore
from hestia.persistence.db import Database


@pytest.fixture
async def memory_store():
    """Create a MemoryStore with a fresh in-memory database."""
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.connect()
    await db.create_tables()
    store = MemoryStore(db)
    await store.create_table()
    yield store
    await db.close()


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_marks_inactive_and_search_excludes_it(self, memory_store):
        """Soft-deleting a memory excludes it from search and list results."""
        mem = await memory_store.save(
            content="Soft delete me", platform="cli", platform_user="alice"
        )

        deleted = await memory_store.soft_delete(
            mem.id, platform="cli", platform_user="alice", reason="pruned"
        )
        assert deleted is True

        fetched = await memory_store.get(mem.id)
        assert fetched is not None
        assert fetched.is_active is False
        assert fetched.deleted_reason == "pruned"
        assert fetched.deleted_at is not None

        search_results = await memory_store.search(
            "delete", platform="cli", platform_user="alice"
        )
        assert search_results == []

        list_results = await memory_store.list_memories(
            platform="cli", platform_user="alice"
        )
        assert list_results == []

    @pytest.mark.asyncio
    async def test_restore_brings_memory_back(self, memory_store):
        """Restoring a soft-deleted memory makes it active again."""
        mem = await memory_store.save(
            content="Restore me", platform="cli", platform_user="alice"
        )
        await memory_store.soft_delete(mem.id, platform="cli", platform_user="alice")

        restored = await memory_store.restore(
            mem.id, platform="cli", platform_user="alice"
        )
        assert restored is True

        fetched = await memory_store.get(mem.id)
        assert fetched is not None
        assert fetched.is_active is True
        assert fetched.deleted_at is None
        assert fetched.deleted_reason is None

        search_results = await memory_store.search(
            "Restore", platform="cli", platform_user="alice"
        )
        assert len(search_results) == 1


class TestProtectedSet:
    @pytest.mark.asyncio
    async def test_protected_set_flags_block_soft_delete(self, memory_store):
        """Pinned, user-authored, and recently-recalled memories are protected."""
        pinned = await memory_store.save(
            content="Pinned memory", platform="cli", platform_user="alice"
        )
        await memory_store.pin(pinned.id, pinned=True, allow_unscoped=True)
        pinned = await memory_store.get(pinned.id)
        assert memory_store.is_protected(pinned) is True

        authored = await memory_store.save(
            content="User-authored memory", platform="cli", platform_user="alice"
        )
        await memory_store.mark_user_authored(authored.id, allow_unscoped=True)
        authored = await memory_store.get(authored.id)
        assert memory_store.is_protected(authored) is True

        recalled = await memory_store.save(
            content="Recently recalled memory", platform="cli", platform_user="alice"
        )
        await memory_store.mark_recalled(recalled.id, allow_unscoped=True)
        recalled = await memory_store.get(recalled.id)
        assert memory_store.is_protected(recalled) is True

    @pytest.mark.asyncio
    async def test_pin_user_authored_and_recalled_helpers(self, memory_store):
        """Pin, mark_user_authored, and mark_recalled update the correct flags."""
        mem = await memory_store.save(
            content="Helper test", platform="cli", platform_user="alice"
        )

        assert await memory_store.pin(mem.id, pinned=True, allow_unscoped=True) is True
        fetched = await memory_store.get(mem.id)
        assert fetched.is_pinned is True

        assert await memory_store.mark_user_authored(mem.id, allow_unscoped=True) is True
        fetched = await memory_store.get(mem.id)
        assert fetched.is_user_authored is True

        assert await memory_store.mark_recalled(mem.id, allow_unscoped=True) is True
        fetched = await memory_store.get(mem.id)
        assert fetched.last_recalled_at is not None


class TestActiveInactiveLists:
    @pytest.mark.asyncio
    async def test_list_active_and_inactive(self, memory_store):
        """list_active_memories and list_inactive_memories partition correctly."""
        active = await memory_store.save(
            content="Active memory", platform="cli", platform_user="alice"
        )
        inactive = await memory_store.save(
            content="Inactive memory", platform="cli", platform_user="alice"
        )
        await memory_store.soft_delete(
            inactive.id, platform="cli", platform_user="alice"
        )

        active_results = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active_results) == 1
        assert active_results[0].id == active.id

        inactive_results = await memory_store.list_inactive_memories(
            platform="cli", platform_user="alice"
        )
        assert len(inactive_results) == 1
        assert inactive_results[0].id == inactive.id

    @pytest.mark.asyncio
    async def test_list_memories_defaults_to_active_only(self, memory_store):
        """list_memories omits soft-deleted rows by default."""
        await memory_store.save(
            content="Active memory", platform="cli", platform_user="alice"
        )
        inactive = await memory_store.save(
            content="Inactive memory", platform="cli", platform_user="alice"
        )
        await memory_store.soft_delete(
            inactive.id, platform="cli", platform_user="alice"
        )

        results = await memory_store.list_memories(
            platform="cli", platform_user="alice"
        )
        assert len(results) == 1
        assert results[0].content == "Active memory"

    @pytest.mark.asyncio
    async def test_list_memories_include_inactive(self, memory_store):
        """list_memories with include_inactive=True returns soft-deleted rows."""
        await memory_store.save(
            content="Active memory", platform="cli", platform_user="alice"
        )
        inactive = await memory_store.save(
            content="Inactive memory", platform="cli", platform_user="alice"
        )
        await memory_store.soft_delete(
            inactive.id, platform="cli", platform_user="alice"
        )

        results = await memory_store.list_memories(
            platform="cli", platform_user="alice", include_inactive=True
        )
        assert len(results) == 2


class TestMemoryUpdate:
    @pytest.mark.asyncio
    async def test_update_content_and_tags(self, memory_store):
        """Updating content and tags persists changes."""
        mem = await memory_store.save(
            content="Original content here", tags=["a"], platform="cli", platform_user="alice"
        )

        updated = await memory_store.update(
            mem.id,
            content="Updated content here",
            tags=["a", "b"],
            platform="cli",
            platform_user="alice",
        )
        assert updated is True

        fetched = await memory_store.get(mem.id)
        assert fetched is not None
        assert fetched.content == "Updated content here"
        assert fetched.tags == ["a", "b"]

    @pytest.mark.asyncio
    async def test_update_is_global_promotes_and_clears_topics(self, memory_store):
        """Promoting a memory to global clears topic associations."""
        topic_store = TopicStore(memory_store._db)
        topic = await topic_store.get_or_create_topic("cli", "alice", "hobbies")
        mem = await memory_store.save(
            content="I like chess",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic.id],
        )
        topic_ids = await memory_store.get_topic_ids_for_memories([mem.id])
        assert topic_ids[mem.id] == [topic.id]

        updated = await memory_store.update(
            mem.id,
            is_global=True,
            platform="cli",
            platform_user="alice",
        )
        assert updated is True

        fetched = await memory_store.get(mem.id)
        assert fetched is not None
        assert fetched.is_global is True
        topic_ids = await memory_store.get_topic_ids_for_memories([mem.id])
        assert topic_ids[mem.id] == []

    @pytest.mark.asyncio
    async def test_update_topic_ids_changes_retrieval_scope(self, memory_store):
        """Changing a memory's topic IDs moves it between topic scopes."""
        topic_store = TopicStore(memory_store._db)
        topic_a = await topic_store.get_or_create_topic("cli", "alice", "a")
        topic_b = await topic_store.get_or_create_topic("cli", "alice", "b")
        mem = await memory_store.save(
            content="Scoped to a",
            platform="cli",
            platform_user="alice",
            topic_ids=[topic_a.id],
        )

        updated = await memory_store.update(
            mem.id,
            topic_ids=[topic_b.id],
            platform="cli",
            platform_user="alice",
        )
        assert updated is True

        topic_ids = await memory_store.get_topic_ids_for_memories([mem.id])
        assert topic_ids[mem.id] == [topic_b.id]

    @pytest.mark.asyncio
    async def test_update_ignores_soft_deleted_memory(self, memory_store):
        """Updates are rejected for soft-deleted memories."""
        mem = await memory_store.save(
            content="Soon gone", platform="cli", platform_user="alice"
        )
        await memory_store.soft_delete(mem.id, platform="cli", platform_user="alice")

        updated = await memory_store.update(
            mem.id,
            content="Updated content here",
            platform="cli",
            platform_user="alice",
        )
        assert updated is False
