"""Tests for the blocked-actions digest assembler."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from hestia.blocked_actions.digest import (
    BlockedActionsDigest,
    digest_cron_from_time,
    ensure_blocked_digest_task,
)
from hestia.core.clock import utcnow
from hestia.core.types import Session
from hestia.persistence.capability_events import CapabilityEventStore
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.session_store import SessionStore
from hestia.policy import CapabilityRequest, CapabilityResult, Channel, Identity


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def event_store(db: Database) -> CapabilityEventStore:
    return CapabilityEventStore(db)


@pytest.fixture
async def session_store(db: Database) -> SessionStore:
    return SessionStore(db)


@pytest.fixture
async def operator_session(session_store: SessionStore) -> Session:
    return await session_store.get_or_create_session("telegram", "operator-1")


async def _record_denial(
    event_store: CapabilityEventStore,
    *,
    tool_name: str = "terminal",
    channel: Channel = Channel.WORKFLOW,
    workflow_id: str | None = "wf-1",
    injection: bool = False,
    reason: str = "not_allow_listed",
) -> None:
    request = CapabilityRequest(
        actor=Identity(platform="workflow", platform_user=workflow_id or ""),
        channel=channel,
        tool_name=tool_name,
        inputs={"command": "ls"},
        source_workflow_id=workflow_id,
    )
    result = CapabilityResult(
        allowed=False,
        auto_approved=False,
        requires_confirmation=False,
        reason=reason,
    )
    await event_store.record(request, result, injection_flagged=injection)


class TestBlockedActionsDigest:
    async def test_format_digest_returns_none_when_empty(
        self,
        event_store: CapabilityEventStore,
    ) -> None:
        digest = BlockedActionsDigest(event_store)
        assert digest.format_digest([]) is None

    async def test_query_default_window_is_24h(
        self,
        event_store: CapabilityEventStore,
    ) -> None:
        digest = BlockedActionsDigest(event_store)
        await _record_denial(event_store, workflow_id="wf-recent")
        events = await digest.query()
        assert len(events) == 1

        ancient = utcnow() - timedelta(days=2)
        events = await digest.query(since=ancient)
        assert len(events) == 1

        future = utcnow() + timedelta(hours=1)
        events = await digest.query(since=future)
        assert len(events) == 0

    async def test_format_digest_groups_by_origin_and_marks_injection(
        self,
        event_store: CapabilityEventStore,
    ) -> None:
        digest = BlockedActionsDigest(event_store)
        await _record_denial(event_store, workflow_id="wf-a", injection=True)
        await _record_denial(event_store, workflow_id="wf-a", injection=False)
        await _record_denial(event_store, workflow_id="wf-b", injection=False)

        text = digest.format_digest(await event_store.list_recent())
        assert text is not None
        assert "Injection-flagged" in text
        assert "workflow:wf-a" in text
        assert "workflow:wf-b" in text
        assert "terminal" in text

    async def test_send_digest_returns_silent_when_empty(
        self,
        event_store: CapabilityEventStore,
    ) -> None:
        digest = BlockedActionsDigest(event_store)
        assert await digest.send_digest() == "SILENT"

    async def test_send_digest_for_task_uses_last_run_at(
        self,
        event_store: CapabilityEventStore,
        operator_session: Session,
    ) -> None:
        digest = BlockedActionsDigest(event_store)
        await _record_denial(event_store, workflow_id="wf-1")

        @dataclass
        class FakeTask:
            id: str
            session_id: str
            last_run_at: datetime | None
            created_at: datetime

        fake_task = FakeTask(
            id="task-1",
            session_id=operator_session.id,
            last_run_at=utcnow() - timedelta(hours=1),
            created_at=utcnow() - timedelta(days=1),
        )
        text = await digest.send_digest_for_task(fake_task)  # type: ignore[arg-type]
        assert "blocked-actions digest" in text.lower()
        assert "wf-1" in text

    async def test_digest_cron_from_time(self) -> None:
        assert digest_cron_from_time("09:00") == "0 9 * * *"
        assert digest_cron_from_time("23:30") == "30 23 * * *"

    async def test_ensure_blocked_digest_task_creates_and_updates(
        self,
        db: Database,
        operator_session: Session,
    ) -> None:
        scheduler_store = SchedulerStore(db)
        task1 = await ensure_blocked_digest_task(
            scheduler_store, operator_session.id, "09:00"
        )
        assert task1.task_type == "blocked_digest"
        assert task1.cron_expression == "0 9 * * *"

        task2 = await ensure_blocked_digest_task(
            scheduler_store, operator_session.id, "10:00"
        )
        assert task2.id == task1.id
        assert task2.cron_expression == "0 10 * * *"
