"""Unit tests for deterministic memory prune (L228)."""

from __future__ import annotations

import pytest

from hestia.memory.maintenance.prune import DeterministicPruner, PruneResult
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
def pruner(memory_store):
    """Create a DeterministicPruner bound to the test store."""
    return DeterministicPruner(memory_store)


async def _insert_memory(
    store: MemoryStore,
    *,
    content: str,
    platform: str | None = None,
    platform_user: str | None = None,
    is_pinned: bool = False,
    is_user_authored: bool = False,
) -> str:
    """Insert a memory row directly, bypassing the write-time sanitizer."""
    import uuid

    from hestia.core.clock import utcnow

    memory_id = f"mem_{uuid.uuid4().hex[:16]}"
    async with store._db.engine.connect() as conn:
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                "INSERT INTO memory (id, content, tags, session_id, created_at, "
                "platform, platform_user, is_active, deleted_at, deleted_reason, "
                "superseded_by, is_pinned, is_user_authored, last_recalled_at) "
                "VALUES (:id, :content, :tags, :session_id, :created_at, "
                ":platform, :platform_user, :is_active, :deleted_at, :deleted_reason, "
                ":superseded_by, :is_pinned, :is_user_authored, :last_recalled_at)"
            ),
            {
                "id": memory_id,
                "content": content,
                "tags": "",
                "session_id": None,
                "created_at": utcnow().isoformat(),
                "platform": platform,
                "platform_user": platform_user,
                "is_active": 1,
                "deleted_at": None,
                "deleted_reason": None,
                "superseded_by": None,
                "is_pinned": 1 if is_pinned else 0,
                "is_user_authored": 1 if is_user_authored else 0,
                "last_recalled_at": None,
            },
        )
        await conn.commit()
    return memory_id


class TestJunkPruning:
    @pytest.mark.asyncio
    async def test_junk_memory_is_pruned(self, memory_store, pruner):
        """A memory with sanitizer-rejected content is soft-deleted as junk."""
        memory_id = await _insert_memory(
            memory_store,
            content="<tool_call>foo</tool_call>",
            platform="cli",
            platform_user="alice",
        )

        result = await pruner.run("cli", "alice")

        assert result == PruneResult(junk_count=1, orphan_count=0)

        memory = await memory_store.get(memory_id)
        assert memory is not None
        assert memory.is_active is False
        assert memory.deleted_reason == "junk"


class TestOrphanPruning:
    @pytest.mark.asyncio
    async def test_unscoped_memory_is_pruned(self, memory_store, pruner):
        """A valid memory without platform/user scope is soft-deleted as orphan."""
        memory_id = await _insert_memory(
            memory_store,
            content="I love hiking in the mountains",
            platform=None,
            platform_user=None,
        )

        result = await pruner.run()

        assert result == PruneResult(junk_count=0, orphan_count=1)

        memory = await memory_store.get(memory_id)
        assert memory is not None
        assert memory.is_active is False
        assert memory.deleted_reason == "orphan"


class TestValidMemoryPreservation:
    @pytest.mark.asyncio
    async def test_valid_old_fact_is_not_pruned(self, memory_store, pruner):
        """A normal, scoped, non-junk memory survives the prune pass."""
        memory_id = await _insert_memory(
            memory_store,
            content="The user prefers dark mode in all applications.",
            platform="cli",
            platform_user="alice",
        )

        result = await pruner.run("cli", "alice")

        assert result == PruneResult(junk_count=0, orphan_count=0)

        memory = await memory_store.get(memory_id)
        assert memory is not None
        assert memory.is_active is True


class TestProtectedMemories:
    @pytest.mark.asyncio
    async def test_protected_junk_memory_is_not_pruned(self, memory_store, pruner):
        """A pinned junk memory is protected and remains active."""
        memory_id = await _insert_memory(
            memory_store,
            content="<tool_call>bar</tool_call>",
            platform="cli",
            platform_user="alice",
            is_pinned=True,
        )

        result = await pruner.run("cli", "alice")

        assert result == PruneResult(junk_count=0, orphan_count=0)

        memory = await memory_store.get(memory_id)
        assert memory is not None
        assert memory.is_active is True


class TestScopedPruning:
    @pytest.mark.asyncio
    async def test_prune_scopes_to_identity(self, memory_store, pruner):
        """Pruning scoped to one identity only affects that identity."""
        alice_id = await _insert_memory(
            memory_store,
            content="<function>bad</function>",
            platform="cli",
            platform_user="alice",
        )
        bob_id = await _insert_memory(
            memory_store,
            content="<function>bad</function>",
            platform="cli",
            platform_user="bob",
        )

        result = await pruner.run("cli", "alice")

        assert result == PruneResult(junk_count=1, orphan_count=0)

        alice = await memory_store.get(alice_id)
        bob = await memory_store.get(bob_id)
        assert alice is not None
        assert alice.is_active is False
        assert bob is not None
        assert bob.is_active is True
