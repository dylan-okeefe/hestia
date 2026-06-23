"""Tests that the scheduler routes memory maintenance tasks."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Session
from hestia.memory.maintenance import MemoryMaintenance
from hestia.memory.maintenance.digest import MemoryMaintenanceDigest
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
    memory_maintenance: MemoryMaintenance,
    digest: MemoryMaintenanceDigest,
) -> Scheduler:
    return Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=orchestrator,
        response_callback=AsyncMock(),
        tick_interval_seconds=60.0,
        memory_maintenance=memory_maintenance,
        memory_maintenance_digest=digest,
    )


@pytest.mark.asyncio
async def test_scheduler_runs_deterministic_task(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    """A memory_maintenance_deterministic task runs the deterministic pass."""
    orchestrator = MagicMock()
    orchestrator.process_turn = AsyncMock()

    maintenance = MagicMock(spec=MemoryMaintenance)
    maintenance.run_deterministic_pass = AsyncMock(return_value=(MagicMock(), MagicMock()))

    digest = MagicMock(spec=MemoryMaintenanceDigest)
    digest.send_digest_for_task = AsyncMock(return_value="deterministic digest")

    scheduler = _make_scheduler(
        scheduler_store, session_store, orchestrator, maintenance, digest
    )

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt='{"platform": "cli", "platform_user": "alice"}',
        cron_expression="0 3 * * *",
        task_type="memory_maintenance_deterministic",
        notify=False,
    )

    await scheduler.run_now(task.id)

    maintenance.run_deterministic_pass.assert_awaited_once_with("cli", "alice")
    digest.send_digest_for_task.assert_awaited_once_with(task)
    cast(AsyncMock, scheduler._response_callback).assert_awaited_once_with(
        task, "deterministic digest"
    )
    orchestrator.process_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_runs_llm_task(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    """A memory_maintenance_llm task runs the LLM pass."""
    orchestrator = MagicMock()
    orchestrator.process_turn = AsyncMock()

    maintenance = MagicMock(spec=MemoryMaintenance)
    maintenance.run_llm_pass = AsyncMock(return_value=(MagicMock(), MagicMock()))

    digest = MagicMock(spec=MemoryMaintenanceDigest)
    digest.send_digest_for_task = AsyncMock(return_value="llm digest")

    scheduler = _make_scheduler(
        scheduler_store, session_store, orchestrator, maintenance, digest
    )

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt='{"platform": "cli", "platform_user": "alice"}',
        cron_expression="0 4 * * 0",
        task_type="memory_maintenance_llm",
        notify=False,
    )

    await scheduler.run_now(task.id)

    maintenance.run_llm_pass.assert_awaited_once_with("cli", "alice")
    digest.send_digest_for_task.assert_awaited_once_with(task)
    cast(AsyncMock, scheduler._response_callback).assert_awaited_once_with(
        task, "llm digest"
    )
    orchestrator.process_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_maintenance_silent_skips_delivery(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    """A SILENT digest is still delivered to the response callback."""
    orchestrator = MagicMock()
    maintenance = MagicMock(spec=MemoryMaintenance)
    maintenance.run_deterministic_pass = AsyncMock(return_value=(MagicMock(), MagicMock()))

    digest = MagicMock(spec=MemoryMaintenanceDigest)
    digest.send_digest_for_task = AsyncMock(return_value="SILENT")

    scheduler = _make_scheduler(
        scheduler_store, session_store, orchestrator, maintenance, digest
    )

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt='{"platform": "cli", "platform_user": "alice"}',
        cron_expression="0 3 * * *",
        task_type="memory_maintenance_deterministic",
        notify=True,
    )

    await scheduler.run_now(task.id)

    cast(AsyncMock, scheduler._response_callback).assert_awaited_once_with(task, "SILENT")


@pytest.mark.asyncio
async def test_scheduler_maintenance_missing_service_reports_error(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    operator_session: Session,
) -> None:
    """A maintenance task errors when the service is not configured."""
    scheduler = Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=MagicMock(),
        response_callback=AsyncMock(),
        tick_interval_seconds=60.0,
    )

    task = await scheduler_store.create_task(
        session_id=operator_session.id,
        prompt='{"platform": "cli", "platform_user": "alice"}',
        cron_expression="0 3 * * *",
        task_type="memory_maintenance_deterministic",
    )

    await scheduler.run_now(task.id)

    updated = await scheduler_store.get_task(task.id)
    assert updated is not None
    assert updated.last_error is not None
    assert "Memory maintenance service not configured" in updated.last_error
