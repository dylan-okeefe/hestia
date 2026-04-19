"""Unit tests for StyleProfileBuilder metric computations."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from hestia.config import StyleConfig
from hestia.core.clock import utcnow
from hestia.core.types import SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.schema import sessions, turns, messages, traces
from hestia.memory.store import MemoryStore
from hestia.style.builder import StyleProfileBuilder
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
    config = StyleConfig(enabled=True, lookback_days=30)
    return StyleProfileBuilder(db, style_store, config)


async def _insert_session(db, session_id, platform="cli", platform_user="default", since=None):
    if since is None:
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


class TestPreferredLength:
    async def test_median_excludes_feedback(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        await _insert_turn(db, "t1", "s1", since)
        await _insert_trace(db, "tr1", "s1", "t1", since, 100)
        # User then asks for shorter
        await _insert_message(db, "s1", 0, "user", "make it shorter", since + timedelta(seconds=1))

        await _insert_turn(db, "t2", "s1", since + timedelta(minutes=1))
        await _insert_trace(db, "tr2", "s1", "t2", since + timedelta(minutes=1), 200)
        # No feedback after t2

        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "preferred_length")
        assert metric is not None
        # Only t2 qualifies (200 tokens)
        assert metric.value_json == "200"

    async def test_median_with_multiple(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        for i, tokens in enumerate([100, 200, 300]):
            turn_id = f"t{i}"
            trace_id = f"tr{i}"
            ts = since + timedelta(minutes=i)
            await _insert_turn(db, turn_id, "s1", ts)
            await _insert_trace(db, trace_id, "s1", turn_id, ts, tokens)

        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "preferred_length")
        assert metric is not None
        assert metric.value_json == "200"

    async def test_none_when_no_traces(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "preferred_length")
        assert metric is None


class TestFormality:
    async def test_casual_messages(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        await _insert_message(db, "s1", 0, "user", "hey what's up", since)
        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "formality")
        assert metric is not None
        assert float(metric.value_json) == 0.0

    async def test_technical_messages(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        await _insert_message(
            db, "s1", 0, "user", "the api endpoint returns a json array", since
        )
        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "formality")
        assert metric is not None
        # "the api endpoint returns a json array" -> 7 words, 4 technical
        assert float(metric.value_json) == pytest.approx(4 / 7, rel=1e-2)


class TestTopTopics:
    async def test_empty_without_memories(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "top_topics")
        assert metric is not None
        assert metric.value_json == "[]"


class TestActivityWindow:
    async def test_histogram(self, db, style_store, builder):
        since = utcnow() - timedelta(days=1)
        await _insert_session(db, "s1", since=since)
        for i in range(3):
            turn_id = f"t{i}"
            ts = since.replace(hour=14, minute=i)
            await _insert_turn(db, turn_id, "s1", ts)

        await builder.build_all()
        metric = await style_store.get_metric("cli", "default", "activity_window")
        assert metric is not None
        hist = __import__("json").loads(metric.value_json)
        assert hist[14] == 3
        assert sum(hist) == 3
