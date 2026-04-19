"""Integration tests for style profile lifecycle."""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from hestia.config import StyleConfig
from hestia.core.clock import utcnow
from hestia.core.types import SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.schema import sessions, turns, messages, traces
from hestia.memory.store import MemoryStore
from hestia.style.builder import StyleProfileBuilder
from hestia.style.context import format_style_prefix_from_data
from hestia.style.scheduler import StyleScheduler
from hestia.style.store import StyleProfileStore


@pytest.fixture
async def db(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.connect()
    await db.create_tables()
    memory_store = MemoryStore(db)
    await memory_store.create_table()
    yield db
    await db.close()


@pytest.fixture
async def style_store(db):
    store = StyleProfileStore(db)
    await store.create_table()
    return store


@pytest.fixture
async def builder(db, style_store):
    config = StyleConfig(enabled=True, lookback_days=30, min_turns_to_activate=1)
    return StyleProfileBuilder(db, style_store, config)


async def _insert_session(db, session_id, platform="cli", platform_user="default"):
    since = utcnow() - timedelta(days=1)
    async with db.engine.connect() as conn:
        await conn.execute(
            sa.insert(sessions).values(
                id=session_id,
                platform=platform,
                platform_user=platform_user,
                started_at=since,
                last_active_at=since,
                slot_id=None,
                slot_saved_path=None,
                state=SessionState.ACTIVE.value,
                temperature=SessionTemperature.HOT.value,
            )
        )
        await conn.commit()


async def _insert_turn(db, turn_id, session_id, started_at):
    async with db.engine.connect() as conn:
        await conn.execute(
            sa.insert(turns).values(
                id=turn_id,
                session_id=session_id,
                state="done",
                started_at=started_at,
                last_transition_at=started_at,
                iteration=0,
                reasoning_budget=2048,
            )
        )
        await conn.commit()


async def _insert_message(db, session_id, idx, role, content, created_at):
    async with db.engine.connect() as conn:
        await conn.execute(
            sa.insert(messages).values(
                session_id=session_id,
                idx=idx,
                role=role,
                content=content,
                tool_calls=None,
                tool_call_id=None,
                reasoning_content=None,
                created_at=created_at,
            )
        )
        await conn.commit()


async def _insert_trace(db, trace_id, session_id, turn_id, started_at, completion_tokens):
    async with db.engine.connect() as conn:
        await conn.execute(
            sa.insert(traces).values(
                id=trace_id,
                session_id=session_id,
                turn_id=turn_id,
                started_at=started_at,
                ended_at=started_at,
                user_input_summary="test",
                tools_called="[]",
                tool_call_count=0,
                delegated=0,
                outcome="success",
                artifact_handles="[]",
                prompt_tokens=10,
                completion_tokens=completion_tokens,
                reasoning_tokens=0,
                total_duration_ms=100,
            )
        )
        await conn.commit()


class TestStyleLifecycle:
    async def test_scheduler_builds_profile(self, db, style_store, builder):
        """StyleScheduler tick should trigger a profile rebuild."""
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1")
        await _insert_turn(db, "t1", "s1", since)
        await _insert_trace(db, "tr1", "s1", "t1", since, 150)

        from hestia.persistence.sessions import SessionStore

        session_store = SessionStore(db)
        config = StyleConfig(enabled=True, cron="* * * * *", lookback_days=30)
        scheduler = StyleScheduler(config, builder, session_store)

        # Should run because no session is recently active
        await scheduler.tick(utcnow())

        metric = await style_store.get_metric("cli", "default", "preferred_length")
        assert metric is not None
        assert metric.value_json == "150"

    async def test_context_injection(self, db, style_store, builder):
        """format_style_prefix_from_data produces the expected block."""
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1")
        await _insert_message(db, "s1", 0, "user", "hello api", since)
        await builder.build_all()

        data = await style_store.get_profile_dict("cli", "default")
        prefix = format_style_prefix_from_data(data)
        assert prefix is not None
        assert "[STYLE]" in prefix
        assert "technical" in prefix

    async def test_cli_reset_wipes_profile(self, db, style_store, builder):
        """Reset should delete all metrics for a user."""
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1")
        await _insert_turn(db, "t1", "s1", since)
        await _insert_trace(db, "tr1", "s1", "t1", since, 150)
        await builder.build_all()

        count = await style_store.delete_profile("cli", "default")
        assert count > 0

        metrics = await style_store.list_metrics("cli", "default")
        assert metrics == []

    async def test_cold_start_no_prefix(self, db, style_store):
        """When no data exists, prefix formatter returns None."""
        data = await style_store.get_profile_dict("cli", "default")
        prefix = format_style_prefix_from_data(data)
        assert prefix is None

    async def test_namespaced_per_user(self, db, style_store, builder):
        """Profiles for different users do not cross-talk."""
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", platform="matrix", platform_user="@alice:matrix.org")
        await _insert_turn(db, "t1", "s1", since)
        await _insert_trace(db, "tr1", "s1", "t1", since, 250)

        await _insert_session(db, "s2", platform="matrix", platform_user="@bob:matrix.org")
        await _insert_turn(db, "t2", "s2", since)
        await _insert_trace(db, "tr2", "s2", "t2", since, 350)

        await builder.build_all()

        alice = await style_store.get_metric("matrix", "@alice:matrix.org", "preferred_length")
        bob = await style_store.get_metric("matrix", "@bob:matrix.org", "preferred_length")
        assert alice is not None and alice.value_json == "250"
        assert bob is not None and bob.value_json == "350"
