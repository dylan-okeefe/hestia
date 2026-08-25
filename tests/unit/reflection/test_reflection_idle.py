"""BUG-067 regression: _is_idle must compare timestamps in one format.

The idle check passed `cutoff.isoformat()` (T-separator, no microseconds)
against sessions.last_active_at values written by SessionStore as datetime
objects (space separator, microseconds). SQLite compares TEXT
lexicographically, so 'T' > ' ' made every same-day active session look
older than the cutoff - reflection could fire while the user was typing.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from hestia.core.clock import utcnow
from hestia.persistence.db import Database
from hestia.persistence.session_store import SessionStore
from hestia.reflection.scheduler import ReflectionScheduler


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


def _scheduler(session_store: SessionStore, idle_minutes: int) -> ReflectionScheduler:
    config = SimpleNamespace(cron="0 3 * * *", idle_minutes=idle_minutes)
    return ReflectionScheduler(
        config=config,
        runner=None,  # type: ignore[arg-type]  # _is_idle never touches it
        session_store=session_store,
    )


@pytest.mark.asyncio
async def test_recently_active_session_is_not_idle(db) -> None:
    """A session active moments ago must NOT count as idle."""
    store = SessionStore(db)
    await store.get_or_create_session("test", "user-1")
    sched = _scheduler(store, idle_minutes=5)

    assert await sched._is_idle(utcnow()) is False


@pytest.mark.asyncio
async def test_stale_session_counts_as_idle(db) -> None:
    """No session activity inside the idle window -> idle."""
    store = SessionStore(db)
    session = await store.get_or_create_session("test", "user-1")
    from sqlalchemy import text

    stale = utcnow() - timedelta(minutes=30)
    async with db.engine.begin() as conn:
        await conn.execute(
            text("UPDATE sessions SET last_active_at = :ts WHERE id = :id"),
            {"ts": stale, "id": session.id},
        )
    sched = _scheduler(store, idle_minutes=5)

    assert await sched._is_idle(utcnow()) is True
