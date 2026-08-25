"""Tests for memory user scoping (L45b)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from hestia.memory.store import MemoryStore
from hestia.memory.topics import TopicStore
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
        await memory_store.save(content="Alice first note", platform="cli", platform_user="alice")
        await memory_store.save(content="Alice second note", platform="cli", platform_user="alice")
        await memory_store.save(content="Bob first note", platform="cli", platform_user="bob")

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

    @pytest.mark.asyncio
    async def test_save_outside_identity_context_warns(self, memory_store, caplog):
        """M1: saving without identity context logs a warning and writes an unscoped row."""
        import logging

        with caplog.at_level(logging.WARNING):
            mem = await memory_store.save(content="Orphan note")

        assert mem.platform is None
        assert mem.platform_user is None
        assert "memory.save called outside an identity context" in caplog.text

    @pytest.mark.asyncio
    async def test_save_partial_identity_context_warns_and_unscopes(self, memory_store, caplog):
        """M2: saving with only one of platform/platform_user logs warning and writes unscoped."""
        import logging

        with caplog.at_level(logging.WARNING):
            mem = await memory_store.save(
                content="Partial note", platform="cli", platform_user=None
            )

        assert mem.platform is None
        assert mem.platform_user is None
        assert "Partial identity context" in caplog.text

    @pytest.mark.asyncio
    async def test_search_partial_identity_context_returns_empty(self, memory_store, caplog):
        """M5: partial identity context returns empty list (fail-closed)."""
        import logging

        await memory_store.save(content="Scoped note", platform="cli", platform_user="test")
        await memory_store.save(content="Unscoped note")

        with caplog.at_level(logging.WARNING):
            results = await memory_store.search("note", platform="cli", platform_user=None)

        # Partial scope → fail-closed → returns empty
        assert results == []
        assert "Partial identity context" in caplog.text

    @pytest.mark.asyncio
    async def test_search_unscoped_returns_empty(self, memory_store):
        """M5: search without platform_user returns empty list, not all memories."""
        await memory_store.save(content="Alice private", platform="cli", platform_user="alice")
        await memory_store.save(content="Bob private", platform="cli", platform_user="bob")

        # Unscoped search should return empty, not all memories
        results = await memory_store.search("private")
        assert results == []


class TestMemoryToolsUserScope:
    @pytest.fixture
    async def tools(self, tmp_path):
        """Create memory tools bound to a fresh MemoryStore."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()

        topic_store = TopicStore(db)

        search_tool = make_search_memory_tool(store)
        save_tool = make_save_memory_tool(store, topic_store)
        list_tool = make_list_memories_tool(store)
        delete_tool = make_delete_memory_tool(store)

        yield store, topic_store, search_tool, save_tool, list_tool, delete_tool
        await db.close()

    @pytest.mark.asyncio
    async def test_save_memory_tool_uses_contextvar_identity(self, tools):
        """save_memory records platform/platform_user from runtime ContextVars."""
        store, _, _, save_tool, _, _ = tools

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
        store, _, search_tool, save_tool, _, _ = tools

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
        store, _, _, save_tool, list_tool, _ = tools

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
        await like_store.save(
            content="Work task", tags=["work"], platform="cli", platform_user="test"
        )
        await like_store.save(
            content="Personal task", tags=["personal"], platform="cli", platform_user="test"
        )

        results = await like_store.list_memories(tag="work", platform="cli", platform_user="test")
        assert len(results) == 1
        assert "Work task" in results[0].content

    @pytest.mark.asyncio
    async def test_like_fallback_no_false_tag_match(self, like_store):
        """LIKE fallback does not match partial tag tokens."""
        await like_store.save(
            content="Documentation", tags=["docs"], platform="cli", platform_user="test"
        )
        await like_store.save(
            content="Doctor appointment", tags=["doctor"], platform="cli", platform_user="test"
        )

        results = await like_store.list_memories(tag="doc", platform="cli", platform_user="test")
        assert len(results) == 0

        results = await like_store.list_memories(tag="docs", platform="cli", platform_user="test")
        assert len(results) == 1
        assert "Documentation" in results[0].content

    @pytest.mark.asyncio
    async def test_like_fallback_matches_fts5_result_set_for_trivial_query(
        self, like_store, tmp_path
    ):
        """T-8: the FTS5 and LIKE paths return the same IDs for a trivial search.

        Seeded identically on both stores, a single-token query must produce
        the same set of memory IDs regardless of which path is taken.
        """
        db2 = Database("sqlite+aiosqlite:///:memory:")
        await db2.connect()
        await db2.create_tables()
        fts_store = MemoryStore(db2)
        await fts_store.create_table()
        try:
            seed = [
                ("Python programming tutorial", ["python", "docs"]),
                ("Python snake in a terrarium", ["zoo"]),
                ("Rust memory model notes", ["rust"]),
                ("Bash scripting primer", ["bash"]),
            ]
            for content, tags in seed:
                await like_store.save(
                    content=content, tags=tags, platform="cli", platform_user="t"
                )
                await fts_store.save(
                    content=content, tags=tags, platform="cli", platform_user="t"
                )

            like_hits = await like_store.search(
                "Python", platform="cli", platform_user="t"
            )
            fts_hits = await fts_store.search(
                "Python", platform="cli", platform_user="t"
            )

            like_contents = sorted(m.content for m in like_hits)
            fts_contents = sorted(m.content for m in fts_hits)

            assert like_contents == fts_contents
            assert len(like_contents) == 2
        finally:
            await db2.close()


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
        # (unscoped search is now fail-closed, so verify via get)
        mem = await store.get("mem_old")
        assert mem is not None
        assert mem.platform is None
        assert mem.platform_user is None

        # Verify new saves include platform/platform_user
        mem = await store.save(content="New memory", platform="cli", platform_user="test")
        assert mem.platform == "cli"
        assert mem.platform_user == "test"

        await db.close()



class TestMemoryMutationScopeSEC010:
    """SEC-010: memory mutations must deny when identity is unresolved.

    Default is deny; ``allow_unscoped=True`` is the explicit opt-in for
    system callers (CLI operator, maintenance with its own scope). Every
    test here drives the real MemoryStore methods.
    """

    @pytest.fixture
    async def scoped_store(self, tmp_path):
        """Store with one memory each for alice and bob; ContextVars cleared."""
        current_platform.set(None)
        current_platform_user.set(None)
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()
        alice = await store.save(
            content="alice private note", platform="cli", platform_user="alice"
        )
        bob = await store.save(
            content="bob private note", platform="cli", platform_user="bob"
        )
        yield store, alice, bob
        await db.close()

    @pytest.mark.asyncio
    async def test_delete_denies_without_identity(self, scoped_store):
        store, alice, bob = scoped_store
        assert await store.delete(bob.id) is False

    @pytest.mark.asyncio
    async def test_update_denies_without_identity(self, scoped_store):
        store, alice, bob = scoped_store
        assert (
            await store.update(bob.id, content="tampered") is False
        )
        mem = await store.get(bob.id)
        assert mem is not None and mem.content == "bob private note"

    @pytest.mark.asyncio
    async def test_pin_denies_without_identity(self, scoped_store):
        store, alice, bob = scoped_store
        assert await store.pin(bob.id, pinned=True) is False
        mem = await store.get(bob.id)
        assert mem is not None and mem.is_pinned is False

    @pytest.mark.asyncio
    async def test_mark_user_authored_denies_without_identity(self, scoped_store):
        store, alice, bob = scoped_store
        assert await store.mark_user_authored(bob.id) is False
        mem = await store.get(bob.id)
        assert mem is not None and mem.is_user_authored is False

    @pytest.mark.asyncio
    async def test_mark_recalled_denies_without_identity(self, scoped_store):
        store, alice, bob = scoped_store
        before = (await store.get(bob.id)).last_recalled_at
        assert await store.mark_recalled(bob.id) is False
        assert (await store.get(bob.id)).last_recalled_at == before

    @pytest.mark.asyncio
    async def test_delete_allow_unscoped_deletes_cross_user(self, scoped_store):
        """The explicit maintenance/operator opt-in still deletes."""
        store, alice, bob = scoped_store
        assert await store.delete(bob.id, allow_unscoped=True) is True
        assert await store.get(bob.id) is None

    @pytest.mark.asyncio
    async def test_delete_with_identity_scopes_to_owner(self, scoped_store):
        """Regression guard: resolved identity keeps scoping the statement."""
        store, alice, bob = scoped_store
        current_platform.set("cli")
        current_platform_user.set("alice")
        # Alice's identity cannot delete Bob's row.
        assert await store.delete(bob.id) is False
        assert await store.get(bob.id) is not None
        # ...and does delete her own.
        assert await store.delete(alice.id) is True
        assert await store.get(alice.id) is None

    @pytest.mark.asyncio
    async def test_partial_identity_denies_rather_than_falling_through(
        self, scoped_store
    ):
        store, alice, bob = scoped_store
        current_platform.set("cli")
        current_platform_user.set(None)
        assert await store.delete(bob.id) is False
        assert await store.get(bob.id) is not None

    @pytest.mark.asyncio
    async def test_maintenance_pass_still_updates_without_contextvars(
        self, scoped_store
    ):
        """The real dedupe pass runs with no ContextVars set and its
        update() still lands - the fix must not break maintenance."""
        from hestia.memory.maintenance.dedupe import DeterministicDeduper

        store, alice, bob = scoped_store
        near_dup = await store.save(
            content="alice private note  ",  # whitespace-normalized duplicate
            platform="cli",
            platform_user="alice",
        )
        deduper = DeterministicDeduper(store)
        result = await deduper.run("cli", "alice")

        # The load-bearing assertion: the pass merged the duplicate pair via
        # store.update() while no runtime identity was present - one of the
        # two originals ended up soft-deleted or rewritten.
        assert result.merged_count >= 1
        post = await store.get(near_dup.id)
        assert post is None or post.content != "alice private note  "


class TestSoftDeleteRestoreScopeSEC010:
    """Review round 2 on #58: soft_delete and restore share the fail-open
    shape - same contract as the other five mutations."""

    @pytest.fixture
    async def scoped_store(self, tmp_path):
        current_platform.set(None)
        current_platform_user.set(None)
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()
        await db.create_tables()
        store = MemoryStore(db)
        await store.create_table()
        alice = await store.save(
            content="alice note", platform="cli", platform_user="alice"
        )
        bob = await store.save(
            content="bob note", platform="cli", platform_user="bob"
        )
        yield store, alice, bob
        await db.close()

    @pytest.mark.asyncio
    async def test_soft_delete_denies_without_identity(self, scoped_store):
        store, _alice, bob = scoped_store
        assert await store.soft_delete(bob.id, reason="test") is False
        mem = await store.get(bob.id)
        assert mem is not None and mem.is_active

    @pytest.mark.asyncio
    async def test_restore_denies_without_identity(self, scoped_store):
        store, alice, bob = scoped_store
        assert await store.soft_delete(bob.id, platform="cli", platform_user="bob")
        assert await store.restore(bob.id) is False
        # Still soft-deleted: the unauthenticated restore did nothing.
        mem = await store.get(bob.id)
        assert mem is not None and not mem.is_active

    @pytest.mark.asyncio
    async def test_prune_pass_still_soft_deletes_with_explicit_scope(
        self, scoped_store
    ):
        """Regression guard: a scoped prune pass still lands its soft_delete
        under the deny-by-default contract (maintenance threads its own
        scope).

        NOTE this test passes both pre- and post-fix and is a guard, not a
        red-green demonstration - the two denial tests above carry that.
        An UNSCOPED sweep-all prune cannot be tested here at all: the read
        path (list_active_memories -> list_memories) already fails closed
        on unresolved identity, so sweep-all sees zero rows both before and
        after. That read-path design decision is fenced out of #58.
        """
        import sqlalchemy as sa

        from hestia.memory.maintenance.prune import DeterministicPruner

        store, _alice, bob = scoped_store
        stale = await store.save(
            content="to be emptied",
            platform="cli",
            platform_user="bob",
        )
        # save() sanitizes, so empty the content below the sanitizer to
        # manufacture a row the pruner classifies as orphan.
        async with store._db.engine.begin() as conn:
            await conn.execute(
                sa.text("UPDATE memory SET content = '' WHERE id = :id"),
                {"id": stale.id},
            )

        pruner = DeterministicPruner(store)
        result = await pruner.run(platform="cli", platform_user="bob")

        assert result.junk_count + result.orphan_count >= 1
        mem = await store.get(stale.id)
        assert mem is not None and not mem.is_active
