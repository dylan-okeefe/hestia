"""Tests for the memory maintenance digest assembler."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

import pytest

from hestia.core.clock import utcnow
from hestia.memory.maintenance.digest import MemoryMaintenanceDigest
from hestia.memory.maintenance.trace import MaintenanceAction
from hestia.persistence.db import Database
from hestia.persistence.maintenance_trace_store import MaintenanceTraceStore


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def trace_store(db: Database) -> MaintenanceTraceStore:
    store = MaintenanceTraceStore(db)
    await store.create_table()
    return store


@pytest.fixture
def digest(trace_store: MaintenanceTraceStore) -> MemoryMaintenanceDigest:
    return MemoryMaintenanceDigest(trace_store=trace_store)


def _make_action(
    action: str,
    winner: str | None = None,
    losers: list[str] | None = None,
    reason: str = "test",
    details: dict | None = None,
    created_at: datetime | None = None,
) -> MaintenanceAction:
    now = created_at or utcnow()
    return MaintenanceAction(
        id=f"maint_{hash((action, winner, tuple(losers or []), now)) & 0xFFFFFFFF:08x}",
        action=action,
        identity_platform="cli",
        identity_user="alice",
        winner_memory_id=winner,
        loser_memory_ids=losers or [],
        reason=reason,
        created_at=now,
        undoable_until=now + timedelta(days=7),
        details=details or {},
    )


@pytest.mark.asyncio
async def test_digest_formats_supersessions_prominently(
    trace_store: MaintenanceTraceStore,
    digest: MemoryMaintenanceDigest,
) -> None:
    """Supersessions are highlighted at the top of the digest."""
    await trace_store.record(
        _make_action(
            "supersede",
            winner="mem_winner",
            losers=["mem_loser"],
            reason="superseded",
            details={"attribute": "location", "confidence": 0.91},
        )
    )
    await trace_store.record(
        _make_action(
            "merge",
            winner="mem_a",
            losers=["mem_b"],
            reason="deduplicated",
            details={"phase": "exact"},
        )
    )

    text = await digest.send_digest(platform="cli", platform_user="alice")

    assert text != "SILENT"
    supersession_pos = text.lower().find("supersession")
    merge_pos = text.lower().find("merge")
    assert supersession_pos < merge_pos
    assert "mem_loser" in text
    assert "mem_winner" in text
    assert "location" in text


@pytest.mark.asyncio
async def test_digest_returns_silent_when_no_actions(
    trace_store: MaintenanceTraceStore,
    digest: MemoryMaintenanceDigest,
) -> None:
    """An empty window returns SILENT."""
    text = await digest.send_digest(platform="cli", platform_user="alice")
    assert text == "SILENT"


@pytest.mark.asyncio
async def test_digest_includes_undo_deadline(
    trace_store: MaintenanceTraceStore,
    digest: MemoryMaintenanceDigest,
) -> None:
    """The digest reports the soonest undo deadline."""
    await trace_store.record(
        _make_action(
            "prune",
            losers=["mem_junk"],
            reason="junk",
        )
    )

    text = await digest.send_digest(platform="cli", platform_user="alice")

    assert text != "SILENT"
    assert "Undo deadline" in text


@pytest.mark.asyncio
async def test_digest_respects_since_window(
    trace_store: MaintenanceTraceStore,
    digest: MemoryMaintenanceDigest,
) -> None:
    """Actions before the since window are not included."""
    old = _make_action(
        "prune",
        losers=["mem_old"],
        reason="junk",
        created_at=utcnow() - timedelta(days=2),
    )
    new = _make_action(
        "prune",
        losers=["mem_new"],
        reason="junk",
    )
    await trace_store.record(old)
    await trace_store.record(new)

    text = await digest.send_digest(
        since=utcnow() - timedelta(hours=1),
        platform="cli",
        platform_user="alice",
    )

    assert text != "SILENT"
    assert "mem_old" not in text
    # The digest groups prunes by reason, so the returned text reports counts.
    assert "Prunes (1)" in text
