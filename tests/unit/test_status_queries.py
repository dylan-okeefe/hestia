"""Tests for status command query methods."""

from datetime import datetime, timedelta

import pytest

from hestia.core.types import Message
from hestia.orchestrator.types import Turn, TurnState
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore


class TestSessionStoreQueries:
    """Tests for SessionStore status query methods."""

    @pytest.fixture
    async def session_store(self, tmp_path):
        """Create a SessionStore with a fresh database."""
        db_path = tmp_path / "test.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        store = SessionStore(db)
        await db.connect()
        await db.create_tables()
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_count_sessions_by_state_empty(self, session_store):
        """Empty database returns empty dict."""
        counts = await session_store.count_sessions_by_state()
        assert counts == {}

    @pytest.mark.asyncio
    async def test_count_sessions_by_state(self, session_store):
        """Counts sessions grouped by state."""
        # Create sessions in different states
        s1 = await session_store.create_session("cli", "user1")
        await session_store.create_session("cli", "user2")
        await session_store.create_session("cli", "user3")

        # Archive one session
        await session_store.archive_session(s1.id)

        counts = await session_store.count_sessions_by_state()
        assert counts["active"] == 2
        assert counts["archived"] == 1

    @pytest.mark.asyncio
    async def test_turn_stats_since_empty(self, session_store):
        """No turns returns empty dict."""
        since = datetime.now() - timedelta(hours=24)
        stats = await session_store.turn_stats_since(since)
        assert stats == {}

    @pytest.mark.asyncio
    async def test_turn_stats_since_filters_by_time(self, session_store):
        """Only counts turns since the given time."""
        session = await session_store.create_session("cli", "user1")

        # Create a turn in DONE state
        turn = Turn(
            id="turn_1",
            session_id=session.id,
            state=TurnState.DONE,
            user_message=Message(role="user", content="test"),
            started_at=datetime.now(),
            iterations=0,
            tool_calls_made=0,
        )
        await session_store.insert_turn(turn)

        # Query for last hour - should find it
        since = datetime.now() - timedelta(hours=1)
        stats = await session_store.turn_stats_since(since)
        assert stats.get("done") == 1

        # Query for future - should not find it
        since = datetime.now() + timedelta(hours=1)
        stats = await session_store.turn_stats_since(since)
        assert stats == {}


class TestSchedulerStoreQueries:
    """Tests for SchedulerStore status query methods."""

    @pytest.fixture
    async def scheduler_store(self, tmp_path):
        """Create a SchedulerStore with a fresh database."""
        db_path = tmp_path / "test.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        store = SchedulerStore(db)
        await db.connect()
        await db.create_tables()
        yield store
        await db.close()

    @pytest.mark.asyncio
    async def test_summary_stats_empty(self, scheduler_store):
        """Empty database returns zero enabled, None next_run."""
        stats = await scheduler_store.summary_stats()
        assert stats["enabled_count"] == 0
        assert stats["next_run_at"] is None

    @pytest.mark.asyncio
    async def test_summary_stats_with_tasks(self, scheduler_store):
        """Counts enabled tasks and finds earliest next_run_at."""
        # Create enabled task
        await scheduler_store.create_task(
            session_id="s1",
            prompt="Task 1",
            cron_expression="0 9 * * *",
        )

        # Create disabled task
        await scheduler_store.create_task(
            session_id="s2",
            prompt="Task 2",
            cron_expression="0 10 * * *",
            enabled=False,
        )

        stats = await scheduler_store.summary_stats()
        assert stats["enabled_count"] == 1
        assert stats["next_run_at"] is not None
