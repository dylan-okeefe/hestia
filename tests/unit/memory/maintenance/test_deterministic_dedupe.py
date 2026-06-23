"""Unit tests for deterministic memory deduplication (L227)."""

from __future__ import annotations

import asyncio

import pytest

from hestia.memory.maintenance.dedupe import DeterministicDeduper
from hestia.memory.store import MemoryStore
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


@pytest.fixture
def deduper(memory_store):
    """Create a DeterministicDeduper bound to the test store."""
    return DeterministicDeduper(memory_store)


class TestExactDuplicates:
    @pytest.mark.asyncio
    async def test_exact_duplicates_are_merged(self, memory_store, deduper):
        """Two active memories with the same normalized text are merged."""
        await memory_store.save(
            content="Duplicate content",
            tags=["a"],
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="duplicate  content",
            tags=["b"],
            platform="cli",
            platform_user="alice",
        )

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        assert result.skipped_protected_count == 0

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 1
        winner = active[0]
        assert "duplicate content" in winner.content.lower()

        inactive = await memory_store.list_inactive_memories(
            platform="cli", platform_user="alice"
        )
        assert len(inactive) == 1
        assert inactive[0].id != winner.id
        assert inactive[0].deleted_reason == "deduplicated"
        assert inactive[0].superseded_by == winner.id


class TestOverlapDuplicates:
    @pytest.mark.asyncio
    async def test_high_overlap_fts_duplicates_are_merged(self, memory_store, deduper):
        """Memories with high token overlap but different text are merged via FTS."""
        _first = await memory_store.save(
            content="Alice really enjoys pizza pasta weekends daily",
            tags=["food"],
            platform="cli",
            platform_user="alice",
        )
        await asyncio.sleep(0.01)
        second = await memory_store.save(
            content="Alice really enjoys pizza pasta weekends",
            tags=["weekend"],
            platform="cli",
            platform_user="alice",
        )

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 1
        winner = active[0]
        assert "pizza" in winner.content
        assert "pasta" in winner.content
        # Newer memory should win.
        assert winner.id == second.id


class TestProtectedMemories:
    @pytest.mark.asyncio
    async def test_protected_memories_are_skipped(self, memory_store, deduper):
        """Protected memories are not merged and unprotected copies are not forced."""
        protected = await memory_store.save(
            content="Protected duplicate",
            platform="cli",
            platform_user="alice",
        )
        await memory_store.pin(protected.id, pinned=True)
        await memory_store.save(
            content="Protected duplicate",
            platform="cli",
            platform_user="alice",
        )

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 0
        assert result.skipped_protected_count == 1

        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestNonDuplicates:
    @pytest.mark.asyncio
    async def test_non_duplicates_are_left_alone(self, memory_store, deduper):
        """Distinct memories are not merged."""
        await memory_store.save(
            content="I like cats",
            platform="cli",
            platform_user="alice",
        )
        await memory_store.save(
            content="The weather is sunny today",
            platform="cli",
            platform_user="alice",
        )

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 0
        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 2


class TestMergeBehavior:
    @pytest.mark.asyncio
    async def test_merge_uses_newer_and_unions_tags(self, memory_store, deduper):
        """Merge picks the newer memory and unions tags into the winner."""
        older = await memory_store.save(
            content="Project context",
            tags=["project", "alpha"],
            platform="cli",
            platform_user="alice",
        )
        await asyncio.sleep(0.01)
        newer = await memory_store.save(
            content="project context",
            tags=["alpha", "beta"],
            platform="cli",
            platform_user="alice",
        )

        result = await deduper.run("cli", "alice")

        assert result.merged_count == 1
        active = await memory_store.list_active_memories(
            platform="cli", platform_user="alice"
        )
        assert len(active) == 1
        winner = active[0]
        assert winner.id == newer.id
        assert set(winner.tags) == {"project", "alpha", "beta"}

        inactive = await memory_store.list_inactive_memories(
            platform="cli", platform_user="alice"
        )
        assert len(inactive) == 1
        assert inactive[0].id == older.id
        assert inactive[0].superseded_by == winner.id
