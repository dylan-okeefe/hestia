"""Tests that the scheduler routes blocked_digest tasks to the digest service."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.blocked_actions.digest import BlockedActionsDigest
from hestia.core.types import Session
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.session_store import SessionStore
from hestia.scheduler.engine import Scheduler


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def scheduler_store(db: Database) -> SchedulerStore:
    return SchedulerStore(db)


@pytest.fixture
async def session_store(db: Database) -> SessionStore:
    return SessionStore(db)


@pytest.fixture
async def operator_session(session_store: SessionStore) -> Session:
    return await session_store.get_or_create_session("telegram", "operator-1")


def _make_scheduler(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    orchestrator: Any,
    digest: BlockedActionsDigest,
) -> Scheduler:
    return Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=orchestrator,
        response_callback=AsyncMock(),
        tick_interval_seconds=60.0,
        blocked_actions_digest=digest,
    )


@pytest.mark.asyncio
async def test_blocked_digest_task_routes_to_digest_service(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    orchestrator = MagicMock()
    orchestrator.process_turn = AsyncMock()

    digest = MagicMock(spec=BlockedActionsDigest)
    digest.send_digest_for_task = AsyncMock(return_value="digest text")

    scheduler = _make_scheduler(scheduler_store, session_store, orchestrator, digest)

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt="blocked-actions digest",
        cron_expression="0 9 * * *",
        task_type="blocked_digest",
        notify=False,
    )

    await scheduler.run_now(task.id)

    digest.send_digest_for_task.assert_awaited_once_with(task)
    orchestrator.process_turn.assert_not_awaited()
    cast(AsyncMock, scheduler._response_callback).assert_awaited_once_with(task, "digest text")


@pytest.mark.asyncio
async def test_blocked_digest_task_silent_skips_delivery(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    orchestrator = MagicMock()
    digest = MagicMock(spec=BlockedActionsDigest)
    digest.send_digest_for_task = AsyncMock(return_value="SILENT")

    scheduler = _make_scheduler(scheduler_store, session_store, orchestrator, digest)

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt="blocked-actions digest",
        cron_expression="0 9 * * *",
        task_type="blocked_digest",
        notify=True,
    )

    await scheduler.run_now(task.id)

    cast(AsyncMock, scheduler._response_callback).assert_awaited_once_with(task, "SILENT")


@pytest.mark.asyncio
async def test_chat_task_still_uses_orchestrator(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    orchestrator = MagicMock()
    from hestia.orchestrator.types import Turn, TurnState

    orchestrator.process_turn = AsyncMock(
        return_value=Turn(
            id="turn-1",
            session_id=operator_session.id,
            state=TurnState.DONE,
            user_message=MagicMock(),
            started_at=datetime.now(),
        )
    )

    digest = MagicMock(spec=BlockedActionsDigest)

    scheduler = _make_scheduler(scheduler_store, session_store, orchestrator, digest)

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt="hello",
        cron_expression="0 9 * * *",
        task_type="chat",
    )

    await scheduler.run_now(task.id)

    orchestrator.process_turn.assert_awaited_once()
    digest.send_digest_for_task.assert_not_awaited()
