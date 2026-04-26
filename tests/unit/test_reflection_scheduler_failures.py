"""Unit tests for ReflectionScheduler failure visibility."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.scheduler import ReflectionScheduler


class TestReflectionSchedulerFailures:
    """Tests for the failure ring buffer on ReflectionScheduler."""

    @pytest.fixture
    def scheduler(self) -> ReflectionScheduler:
        config = MagicMock()
        config.enabled = True
        config.cron = "0 3 * * *"
        config.idle_minutes = 15

        runner = MagicMock()
        runner._on_failure = None
        store = MagicMock()
        store._db = MagicMock()
        store._db.engine = MagicMock()

        sched = ReflectionScheduler(config, runner, store)
        return sched

    @pytest.mark.asyncio
    async def test_failure_recorded_when_inference_raises(
        self, scheduler: ReflectionScheduler
    ) -> None:
        """Patch runner.run to raise; tick should record failure with stage='tick'."""
        scheduler._is_due = lambda now: True  # type: ignore[method-assign]
        scheduler._is_idle = AsyncMock(return_value=True)  # type: ignore[method-assign]
        scheduler._runner.run = AsyncMock(side_effect=RuntimeError("inference exploded"))  # type: ignore[method-assign]

        proposals = await scheduler.tick()
        assert proposals == []
        assert scheduler.failure_count == 1
        assert len(scheduler.status()["last_errors"]) == 1
        err = scheduler.status()["last_errors"][0]
        assert err["stage"] == "tick"
        assert err["type"] == "RuntimeError"
        assert "inference exploded" in err["message"]

    @pytest.mark.asyncio
    async def test_ring_buffer_caps_at_20(self, scheduler: ReflectionScheduler) -> None:
        """Induce 25 failures; assert buffer length == 20 and oldest entries dropped."""
        scheduler._is_due = lambda now: True  # type: ignore[method-assign]
        scheduler._is_idle = AsyncMock(return_value=True)  # type: ignore[method-assign]
        scheduler._runner.run = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        for _ in range(25):
            await scheduler.tick()

        assert scheduler.failure_count == 25
        assert len(scheduler.status()["last_errors"]) == 20

    def test_status_reports_clean_when_no_failures(self, scheduler: ReflectionScheduler) -> None:
        """Fresh scheduler => status()['ok'] is True."""
        status = scheduler.status()
        assert status["ok"] is True
        assert status["failure_count"] == 0
        assert status["last_errors"] == []
        assert status["last_run_at"] is None


class TestReflectionRunnerFailureCallback:
    """Tests that ReflectionRunner calls on_failure for stage-level errors."""

    @pytest.fixture
    def runner_with_callback(self) -> tuple[ReflectionRunner, MagicMock]:
        config = MagicMock()
        config.enabled = True
        config.lookback_turns = 10
        config.proposals_per_run = 5
        config.expire_days = 14

        inference = MagicMock()
        trace_store = MagicMock()
        trace_store.list_recent = AsyncMock(return_value=[
            MagicMock(
                turn_id="t1",
                session_id="s1",
                user_input_summary="hi",
                tools_called=[],
                outcome="ok",
                delegated=False,
            )
        ])
        proposal_store = MagicMock()

        on_failure = MagicMock()
        runner = ReflectionRunner(
            config, inference, trace_store, proposal_store, on_failure=on_failure
        )
        return runner, on_failure

    @pytest.mark.asyncio
    async def test_mining_failure_calls_on_failure(
        self, runner_with_callback: tuple[ReflectionRunner, MagicMock]
    ) -> None:
        """When inference.chat raises during mining, on_failure('mining', exc) is called."""
        runner, on_failure = runner_with_callback
        runner._inference.chat = AsyncMock(side_effect=RuntimeError("mining failed"))  # type: ignore[method-assign]

        proposals = await runner.run()
        assert proposals == []
        on_failure.assert_called_once()
        args = on_failure.call_args[0]
        assert args[0] == "mining"
        assert isinstance(args[1], RuntimeError)
        assert "mining failed" in str(args[1])

    @pytest.mark.asyncio
    async def test_proposal_failure_calls_on_failure(
        self, runner_with_callback: tuple[ReflectionRunner, MagicMock]
    ) -> None:
        """When inference.chat raises during proposal generation,
        on_failure('proposal', exc) is called."""
        runner, on_failure = runner_with_callback

        # First call (mining) succeeds, second call (proposal) fails
        runner._inference.chat = AsyncMock(  # type: ignore[method-assign]
            return_value=MagicMock(
                content='{"observations": [{"category": "test", "turn_id": "t1", '
                        '"description": "d", "confidence": 0.5}]}'
            )
        )

        # Override to fail on second call
        call_count = 0
        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    content='{"observations": [{"category": "test", "turn_id": "t1", '
                            '"description": "d", "confidence": 0.5}]}'
                )
            raise RuntimeError("proposal failed")

        runner._inference.chat = AsyncMock(side_effect=side_effect)  # type: ignore[method-assign]

        proposals = await runner.run()
        assert proposals == []
        on_failure.assert_called_once()
        args = on_failure.call_args[0]
        assert args[0] == "proposal"
        assert isinstance(args[1], RuntimeError)
        assert "proposal failed" in str(args[1])
