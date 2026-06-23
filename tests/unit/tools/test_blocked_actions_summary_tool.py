"""Tests for the blocked_actions_summary on-demand tool."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from hestia.blocked_actions.digest import BlockedActionsDigest
from hestia.persistence.capability_events import CapabilityEventStore
from hestia.persistence.db import Database
from hestia.policy import CapabilityRequest, CapabilityResult, Channel, Identity
from hestia.tools.builtin.blocked_actions_summary import make_blocked_actions_summary_tool


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


async def _record_denial(event_store: CapabilityEventStore, workflow_id: str) -> None:
    request = CapabilityRequest(
        actor=Identity(platform="workflow", platform_user=workflow_id),
        channel=Channel.WORKFLOW,
        tool_name="terminal",
        inputs={"command": "ls"},
        source_workflow_id=workflow_id,
    )
    result = CapabilityResult(
        allowed=False,
        auto_approved=False,
        requires_confirmation=False,
        reason="not_allow_listed",
    )
    await event_store.record(request, result, injection_flagged=False)


@pytest.mark.asyncio
async def test_blocked_actions_summary_tool_returns_summary(
    event_store: CapabilityEventStore,
) -> None:
    digest = BlockedActionsDigest(event_store)
    tool = make_blocked_actions_summary_tool(digest)

    await _record_denial(event_store, "wf-summary")

    text = await tool(hours=24)
    assert "Blocked actions summary" in text
    assert "wf-summary" in text
    assert "terminal" in text


@pytest.mark.asyncio
async def test_blocked_actions_summary_tool_empty_window(
    event_store: CapabilityEventStore,
) -> None:
    digest = BlockedActionsDigest(event_store)
    tool = make_blocked_actions_summary_tool(digest)

    text = await tool(hours=1)
    assert "No blocked or escalated actions" in text
