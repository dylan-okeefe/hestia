"""TOCTOU regression tests for SessionStore.get_or_create_session.

Pre-v0.8.0, two concurrent calls to ``get_or_create_session`` for the same
``(platform, platform_user)`` could both observe "no active session" and both
INSERT, leaving the database with duplicate ACTIVE rows. The fix is the partial
unique index ``ux_sessions_active_user`` plus an ``INSERT ... ON CONFLICT
DO NOTHING`` upsert that converges concurrent callers on a single session.

These tests:

- Drive 20 coroutines concurrently against a single ``SessionStore`` and assert
  exactly one ACTIVE session results, with all 20 callers receiving the same
  ``Session.id``.
- Verify that a SECOND user — different ``platform_user`` — under the same
  concurrent storm still gets exactly one ACTIVE session of their own. (Guards
  against an over-broad index that would let one user's INSERT block another.)
- Verify that after archiving the active session, the next call creates a new
  one (the partial index excludes ARCHIVED rows, so it must not block a fresh
  INSERT).
- Spot-check the index actually exists in the compiled schema, so a future
  refactor that drops it will fail the unit test instead of silently
  reintroducing the race.
"""

from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa

from hestia.core.types import SessionState
from hestia.persistence.db import Database
from hestia.persistence.schema import sessions
from hestia.persistence.sessions import SessionStore


@pytest.fixture
async def store(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/race.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    yield SessionStore(db)
    await db.close()


async def _count_active(store: SessionStore, platform: str, platform_user: str) -> int:
    query = sa.select(sa.func.count()).select_from(sessions).where(
        sa.and_(
            sessions.c.platform == platform,
            sessions.c.platform_user == platform_user,
            sessions.c.state == SessionState.ACTIVE.value,
        )
    )
    async with store._db.engine.connect() as conn:  # noqa: SLF001 — direct query is the point
        result = await conn.execute(query)
        return int(result.scalar_one())


class TestGetOrCreateSessionRace:
    """Regression tests for the TOCTOU race in get_or_create_session."""

    @pytest.mark.asyncio
    async def test_twenty_concurrent_callers_get_one_session(self, store):
        """20 coroutines for the same user converge on one ACTIVE session."""
        tasks = [store.get_or_create_session("matrix", "@alice:matrix.org") for _ in range(20)]
        sessions_returned = await asyncio.gather(*tasks)

        ids = {s.id for s in sessions_returned}
        assert len(ids) == 1, (
            f"Expected all 20 callers to get the same session id, "
            f"got {len(ids)} distinct ids: {ids}"
        )

        active_count = await _count_active(store, "matrix", "@alice:matrix.org")
        assert active_count == 1, (
            f"Expected exactly 1 ACTIVE row in database, found {active_count}. "
            "The TOCTOU race is back."
        )

    @pytest.mark.asyncio
    async def test_concurrent_storm_for_two_users_does_not_cross(self, store):
        """The partial index is per-user; a storm for user A must not block user B."""
        tasks_a = [store.get_or_create_session("cli", "alice") for _ in range(20)]
        tasks_b = [store.get_or_create_session("cli", "bob") for _ in range(20)]
        results = await asyncio.gather(*tasks_a, *tasks_b)

        alice_results = results[:20]
        bob_results = results[20:]

        alice_ids = {s.id for s in alice_results}
        bob_ids = {s.id for s in bob_results}
        assert len(alice_ids) == 1, f"alice got {len(alice_ids)} sessions: {alice_ids}"
        assert len(bob_ids) == 1, f"bob got {len(bob_ids)} sessions: {bob_ids}"
        assert alice_ids != bob_ids, "alice and bob must not share a session"

        assert await _count_active(store, "cli", "alice") == 1
        assert await _count_active(store, "cli", "bob") == 1

    @pytest.mark.asyncio
    async def test_archive_then_concurrent_recreate(self, store):
        """After archiving, concurrent callers create exactly one new ACTIVE session."""
        original = await store.get_or_create_session("cli", "carol")
        await store.archive_session(original.id)

        tasks = [store.get_or_create_session("cli", "carol") for _ in range(20)]
        results = await asyncio.gather(*tasks)

        ids = {s.id for s in results}
        assert len(ids) == 1
        assert original.id not in ids, "Archived session must not be reused"
        assert await _count_active(store, "cli", "carol") == 1

    @pytest.mark.asyncio
    async def test_partial_unique_index_present(self, store):
        """Guard test: the partial unique index must exist after create_tables."""
        async with store._db.engine.connect() as conn:  # noqa: SLF001
            result = await conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='index'")
            )
            index_names = {row[0] for row in result}
        assert "ux_sessions_active_user" in index_names, (
            "Partial unique index ux_sessions_active_user is missing. "
            "schema.py and migrations/__init__.py must define it."
        )
