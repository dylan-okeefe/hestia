"""Tests for ErrorResolutionStore persistence."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from hestia.persistence.db import Database
from hestia.persistence.error_resolution_store import ErrorResolutionStore


@pytest.fixture
async def resolution_store(tmp_path):
    """Create an ErrorResolutionStore with a fresh database."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.connect()
    await db.create_tables()
    store = ErrorResolutionStore(db)
    yield store
    await db.close()


class TestErrorResolutionStore:
    @pytest.mark.asyncio
    async def test_error_resolutions_table_exists_after_bootstrap(self, tmp_path):
        """Fresh bootstrap via create_tables() must create error_resolutions."""
        db_path = tmp_path / "fresh.db"
        db = Database(f"sqlite+aiosqlite:///{db_path}")
        await db.connect()
        await db.create_tables()

        async with db.engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='error_resolutions'"
                )
            )
            row = result.fetchone()

        await db.close()
        assert row is not None
        assert row[0] == "error_resolutions"

    @pytest.mark.asyncio
    async def test_list_statuses_with_many_ids(self, resolution_store):
        """list_statuses must support IN-clause with many IDs."""
        await resolution_store.set_status("err-1", "resolved", resolved_by="tester")
        await resolution_store.set_status("err-2", "ignored")

        many_ids = [f"err-{i}" for i in range(1, 250)]
        statuses = await resolution_store.list_statuses(many_ids)

        assert statuses["err-1"] == "resolved"
        assert statuses["err-2"] == "ignored"
        assert len(statuses) == 2

    @pytest.mark.asyncio
    async def test_get_and_set_status(self, resolution_store):
        """Basic round-trip for get_status and set_status."""
        assert await resolution_store.get_status("missing") is None

        await resolution_store.set_status("err-a", "resolved", resolved_by="alice")
        assert await resolution_store.get_status("err-a") == "resolved"

        await resolution_store.set_status("err-a", "ignored")
        assert await resolution_store.get_status("err-a") == "ignored"

    @pytest.mark.asyncio
    async def test_list_statuses_empty(self, resolution_store):
        """Empty input returns empty dict without hitting the DB."""
        assert await resolution_store.list_statuses([]) == {}
