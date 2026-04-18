"""Unit tests for StyleScheduler failure visibility."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.style.scheduler import StyleScheduler


class TestStyleSchedulerFailures:
    """Tests for the failure ring buffer on StyleScheduler."""

    @pytest.fixture
    def scheduler(self) -> StyleScheduler:
        config = MagicMock()
        config.enabled = True
        config.cron = "15 3 * * *"

        builder = MagicMock()
        store = MagicMock()
        store._db = MagicMock()
        store._db.engine = MagicMock()

        sched = StyleScheduler(config, builder, store)
        return sched

    @pytest.mark.asyncio
    async def test_failure_recorded_when_build_raises(self, scheduler: StyleScheduler) -> None:
        """Patch builder.build_all to raise; tick should record failure."""
        scheduler._is_due = lambda now: True  # type: ignore[method-assign]
        scheduler._is_idle = AsyncMock(return_value=True)  # type: ignore[method-assign]
        scheduler._builder.build_all = AsyncMock(side_effect=RuntimeError("build exploded"))  # type: ignore[method-assign]

        await scheduler.tick()
        assert scheduler.failure_count == 1
        assert len(scheduler.status()["last_errors"]) == 1
        err = scheduler.status()["last_errors"][0]
        assert err["stage"] == "build"
        assert err["type"] == "RuntimeError"
        assert "build exploded" in err["message"]

    @pytest.mark.asyncio
    async def test_ring_buffer_caps_at_20(self, scheduler: StyleScheduler) -> None:
        """Induce 25 failures; assert buffer length == 20."""
        scheduler._is_due = lambda now: True  # type: ignore[method-assign]
        scheduler._is_idle = AsyncMock(return_value=True)  # type: ignore[method-assign]
        scheduler._builder.build_all = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        for _ in range(25):
            await scheduler.tick()

        assert scheduler.failure_count == 25
        assert len(scheduler.status()["last_errors"]) == 20

    def test_status_reports_clean_when_no_failures(self, scheduler: StyleScheduler) -> None:
        """Fresh scheduler => status()['ok'] is True."""
        status = scheduler.status()
        assert status["ok"] is True
        assert status["failure_count"] == 0
        assert status["last_errors"] == []
        assert status["last_run_at"] is None
