"""Tests for scheduler interaction with the per-session orchestrator lock."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.clock import utcnow
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.session_store import SessionStore
from hestia.scheduler.engine import Scheduler


@pytest.fixture
async def db(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    yield db
    await db.close()


@pytest.fixture
async def session_store(db):
    return SessionStore(db)


@pytest.fixture
async def scheduler_store(db):
    return SchedulerStore(db)


def _make_session(session_id: str = "sess-1") -> Session:
    now = utcnow()
    return Session(
        id=session_id,
        platform="test",
        platform_user="user",
        started_at=now,
        last_active_at=now,
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    orch.process_turn = AsyncMock()
    from hestia.orchestrator.lock import SessionLockManager

    orch._lock_manager = SessionLockManager()
    return orch


@pytest.mark.asyncio
async def test_scheduler_skips_task_when_session_lock_held(
    db, scheduler_store, session_store, mock_orchestrator
):
    """A due task is skipped (not blocked) when its session lock is held."""
    session = await session_store.create_session("test", "user1")
    task = await scheduler_store.create_task(
        session_id=session.id,
        prompt="hello",
        fire_at=utcnow() - timedelta(seconds=1),
    )
    now = utcnow()
    original_next_run = task.next_run_at

    scheduler = Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=mock_orchestrator,
        response_callback=AsyncMock(),
    )

    lock = await mock_orchestrator._lock_manager.acquire(session.id)
    async with lock:
        await scheduler._tick(now)

    mock_orchestrator.process_turn.assert_not_called()
    after_skip = await scheduler_store.get_task(task.id)
    assert after_skip is not None
    assert after_skip.next_run_at == original_next_run


@pytest.mark.asyncio
async def test_scheduler_runs_task_when_session_lock_free(
    db, scheduler_store, session_store, mock_orchestrator
):
    """A due task runs normally when no other turn holds its session lock."""
    session = await session_store.create_session("test", "user2")
    task = await scheduler_store.create_task(
        session_id=session.id,
        prompt="hello",
        fire_at=utcnow() - timedelta(seconds=1),
    )
    now = utcnow()

    mock_orchestrator.process_turn.return_value = MagicMock(error=None)

    scheduler = Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=mock_orchestrator,
        response_callback=AsyncMock(),
    )

    await scheduler._tick(now)

    mock_orchestrator.process_turn.assert_awaited_once()
    after_run = await scheduler_store.get_task(task.id)
    assert after_run is not None
    assert after_run.last_run_at is not None


@pytest.mark.asyncio
async def test_scheduler_runs_other_sessions_while_one_is_locked(
    db, scheduler_store, session_store, mock_orchestrator
):
    """A locked session blocks only its own tasks, not tasks for other sessions."""
    session_a = await session_store.create_session("test", "user-a")
    session_b = await session_store.create_session("test", "user-b")
    task_a = await scheduler_store.create_task(
        session_id=session_a.id,
        prompt="a",
        fire_at=utcnow() - timedelta(seconds=1),
    )
    task_b = await scheduler_store.create_task(
        session_id=session_b.id,
        prompt="b",
        fire_at=utcnow() - timedelta(seconds=1),
    )
    now = utcnow()

    mock_orchestrator.process_turn.return_value = MagicMock(error=None)

    scheduler = Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=mock_orchestrator,
        response_callback=AsyncMock(),
    )

    lock = await mock_orchestrator._lock_manager.acquire(session_a.id)
    async with lock:
        await scheduler._tick(now)

    calls = mock_orchestrator.process_turn.call_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["session"].id == session_b.id

    after_a = await scheduler_store.get_task(task_a.id)
    after_b = await scheduler_store.get_task(task_b.id)
    assert after_a is not None
    assert after_b is not None
    assert after_a.last_run_at is None
    assert after_b.last_run_at is not None
