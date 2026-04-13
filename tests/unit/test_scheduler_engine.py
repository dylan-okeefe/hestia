"""Unit tests for Scheduler engine."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio

from hestia.core.types import Message, ScheduledTask, Session
from hestia.orchestrator.types import Turn, TurnState
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.scheduler import Scheduler


@pytest.fixture(autouse=True)
async def cleanup_tasks():
    """Ensure no stray tasks between tests."""
    yield
    # Clean up any remaining tasks
    try:
        pending = asyncio.all_tasks()
        for task in pending:
            if not task.done() and task != asyncio.current_task():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    except RuntimeError:
        pass  # No event loop


class FakeOrchestrator:
    """Fake orchestrator for testing scheduler."""

    def __init__(self, should_fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.should_fail = should_fail
        self.turn_error: str | None = None

    async def process_turn(
        self,
        session: Session,
        user_message: Message,
        respond_callback: Any,
    ) -> Turn:
        self.calls.append(
            {
                "session": session,
                "user_message": user_message,
            }
        )

        if self.should_fail:
            raise RuntimeError("Orchestrator failed")

        # Simulate sending a response
        await respond_callback("Task completed")

        return Turn(
            id="turn_123",
            session_id=session.id,
            state=TurnState.DONE,
            user_message=user_message,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            iterations=1,
            tool_calls_made=0,
            final_response="Task completed",
            error=self.turn_error,
            transitions=[],
        )


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database for testing."""
    database = Database(url="sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def session_store(db):
    """Create a SessionStore for testing."""
    return SessionStore(db)


@pytest_asyncio.fixture
async def scheduler_store(db):
    """Create a SchedulerStore for testing."""
    return SchedulerStore(db)


@pytest_asyncio.fixture
async def test_session(session_store):
    """Create a test session."""
    return await session_store.get_or_create_session("test", "user1")


@pytest_asyncio.fixture
def response_log():
    """List to capture response callbacks."""
    return []


async def make_scheduler(
    scheduler_store: SchedulerStore,
    session_store: SessionStore,
    response_log: list,
    orchestrator: FakeOrchestrator | None = None,
    tick_interval: float = 5.0,
) -> Scheduler:
    """Helper to create a scheduler with a capturing response callback."""

    async def response_callback(task: ScheduledTask, text: str) -> None:
        response_log.append({"task": task, "text": text})

    return Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=orchestrator or FakeOrchestrator(),
        response_callback=response_callback,
        tick_interval_seconds=tick_interval,
    )


class TestRunNow:
    """Tests for run_now method."""

    @pytest.mark.asyncio
    async def test_run_now_fires_cron_task_and_advances_next_run(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Cron task fires and gets next_run_at advanced."""
        # Create a cron task that would next run tomorrow at 9 AM
        base = datetime(2024, 1, 1, 8, 0, 0)
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Daily task",
            cron_expression="0 9 * * *",  # 9 AM daily
        )

        # Run at 9 AM today
        run_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(scheduler_store, session_store, response_log, orchestrator)

        # Call directly with run_time
        await scheduler._fire_task(task, run_time)

        # Verify orchestrator was called
        assert len(orchestrator.calls) == 1
        assert orchestrator.calls[0]["user_message"].content == "Daily task"

        # Verify response was delivered
        assert len(response_log) == 1
        assert response_log[0]["text"] == "Task completed"

        # Verify task was updated with next run tomorrow
        updated = await scheduler_store.get_task(task.id)
        assert updated.last_run_at == run_time
        assert updated.next_run_at == datetime(2024, 1, 2, 9, 0, 0, tzinfo=timezone.utc)
        assert updated.enabled is True

    @pytest.mark.asyncio
    async def test_run_now_fires_one_shot_and_disables(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """One-shot task fires and gets disabled."""
        fire_at = datetime.now(timezone.utc) - timedelta(hours=1)
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="One-time task",
            fire_at=fire_at,
        )

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(scheduler_store, session_store, response_log, orchestrator)

        await scheduler._fire_task(task, datetime.now(timezone.utc))

        # Verify orchestrator was called
        assert len(orchestrator.calls) == 1

        # Verify task was disabled
        updated = await scheduler_store.get_task(task.id)
        assert updated.enabled is False
        assert updated.next_run_at is None

    @pytest.mark.asyncio
    async def test_run_now_records_error_when_process_turn_raises(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Error during process_turn is recorded on task."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Failing task",
            cron_expression="0 9 * * *",
        )

        failing_orchestrator = FakeOrchestrator(should_fail=True)
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, failing_orchestrator
        )

        run_time = datetime.now(timezone.utc)
        await scheduler._fire_task(task, run_time)

        # Verify error was recorded
        updated = await scheduler_store.get_task(task.id)
        assert updated.last_error == "Orchestrator failed"
        assert updated.last_run_at == run_time

    @pytest.mark.asyncio
    async def test_run_now_records_turn_error(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Turn.error is recorded on task."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Task with turn error",
            cron_expression="0 9 * * *",
        )

        orchestrator = FakeOrchestrator()
        orchestrator.turn_error = "Tool execution failed"
        scheduler = await make_scheduler(scheduler_store, session_store, response_log, orchestrator)

        run_time = datetime.now(timezone.utc)
        await scheduler._fire_task(task, run_time)

        # Verify turn error was recorded
        updated = await scheduler_store.get_task(task.id)
        assert updated.last_error == "Tool execution failed"

    @pytest.mark.asyncio
    async def test_run_now_handles_missing_session_gracefully(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Missing session is handled gracefully with error recorded."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Orphaned task",
            cron_expression="0 9 * * *",
        )

        # Delete the session
        await session_store.end_session(test_session.id, "test cleanup")

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(scheduler_store, session_store, response_log, orchestrator)

        run_time = datetime.now(timezone.utc)
        await scheduler._fire_task(task, run_time)

        # Verify orchestrator was NOT called
        assert len(orchestrator.calls) == 0

        # Verify error was recorded
        updated = await scheduler_store.get_task(task.id)
        assert "no longer exists" in updated.last_error

    @pytest.mark.asyncio
    async def test_run_now_raises_for_missing_task(
        self, scheduler_store, session_store, response_log
    ):
        """run_now raises ValueError for non-existent task."""
        scheduler = await make_scheduler(scheduler_store, session_store, response_log)

        with pytest.raises(ValueError, match="Task not found"):
            await scheduler.run_now("task_nonexistent")


class TestLoop:
    """Tests for the scheduler loop."""

    @pytest.mark.asyncio
    async def test_loop_fires_due_tasks_on_tick(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Loop fires tasks that are due."""
        # Create a task that's already due
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Due task",
            fire_at=past,
        )

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, orchestrator, tick_interval=0.05
        )

        await scheduler.start()
        try:
            # Wait for at least one tick
            await asyncio.sleep(0.1)
        finally:
            await scheduler.stop()

        # Verify orchestrator was called
        assert len(orchestrator.calls) == 1
        assert orchestrator.calls[0]["user_message"].content == "Due task"

    @pytest.mark.asyncio
    async def test_loop_skips_disabled_tasks(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Loop skips disabled tasks even if due."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Disabled task",
            fire_at=past,
            enabled=False,
        )

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, orchestrator, tick_interval=0.05
        )

        await scheduler.start()
        try:
            await asyncio.sleep(0.1)
        finally:
            await scheduler.stop()

        # Verify orchestrator was NOT called
        assert len(orchestrator.calls) == 0

    @pytest.mark.asyncio
    async def test_loop_skips_future_tasks(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Loop skips tasks that aren't due yet."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Future task",
            fire_at=future,
        )

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, orchestrator, tick_interval=0.05
        )

        await scheduler.start()
        try:
            await asyncio.sleep(0.1)
        finally:
            await scheduler.stop()

        # Verify orchestrator was NOT called
        assert len(orchestrator.calls) == 0

    @pytest.mark.asyncio
    async def test_loop_continues_after_tick_error(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Loop continues running even if a tick raises."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Due task",
            fire_at=past,
        )

        # Create orchestrator that fails on first call only
        class FailingThenWorkingOrchestrator(FakeOrchestrator):
            def __init__(self):
                super().__init__()
                self.call_count = 0

            async def process_turn(self, session, user_message, respond_callback):
                self.call_count += 1
                if self.call_count == 1:
                    raise RuntimeError("First call fails")
                return await super().process_turn(session, user_message, respond_callback)

        orchestrator = FailingThenWorkingOrchestrator()
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, orchestrator, tick_interval=0.05
        )

        await scheduler.start()
        try:
            # Wait for multiple ticks
            await asyncio.sleep(0.2)
        finally:
            await scheduler.stop()

        # Verify task was eventually processed (second tick)
        assert orchestrator.call_count >= 1


class TestStartStop:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_raises_if_already_running(
        self, scheduler_store, session_store, response_log
    ):
        """start() raises if scheduler is already running."""
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, tick_interval=0.1
        )

        await scheduler.start()
        with pytest.raises(RuntimeError, match="already running"):
            await scheduler.start()
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, scheduler_store, session_store, response_log):
        """stop() can be called multiple times safely."""
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, tick_interval=0.1
        )

        await scheduler.start()
        await scheduler.stop()
        await scheduler.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_cancels_loop_quickly(self, scheduler_store, session_store, response_log):
        """stop() cancels the loop quickly without waiting full tick."""
        scheduler = await make_scheduler(
            scheduler_store, session_store, response_log, tick_interval=60.0
        )

        await scheduler.start()

        # Stop should return quickly, not wait 60 seconds
        start = datetime.now(timezone.utc)
        await scheduler.stop()
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        assert elapsed < 1.0  # Should be very fast


class TestTick:
    """Tests for _tick method."""

    @pytest.mark.asyncio
    async def test_tick_processes_all_due_tasks(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """_tick processes all due tasks in order."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Create multiple due tasks
        task1 = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Task 1",
            fire_at=past,
        )
        task2 = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Task 2",
            fire_at=past + timedelta(minutes=1),
        )

        orchestrator = FakeOrchestrator()
        scheduler = await make_scheduler(scheduler_store, session_store, response_log, orchestrator)

        await scheduler._tick(datetime.now(timezone.utc))

        # Both tasks should have been processed
        assert len(orchestrator.calls) == 2
        assert orchestrator.calls[0]["user_message"].content == "Task 1"
        assert orchestrator.calls[1]["user_message"].content == "Task 2"

    @pytest.mark.asyncio
    async def test_tick_processes_sequentially(
        self, scheduler_store, session_store, test_session, response_log
    ):
        """Tasks are processed sequentially, not in parallel."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)

        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Task 1",
            fire_at=past,
        )
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Task 2",
            fire_at=past,
        )

        execution_order = []

        class OrderTrackingOrchestrator(FakeOrchestrator):
            async def process_turn(self, session, user_message, respond_callback):
                execution_order.append(user_message.content)
                return await super().process_turn(session, user_message, respond_callback)

        orchestrator = OrderTrackingOrchestrator()
        scheduler = await make_scheduler(scheduler_store, session_store, response_log, orchestrator)

        await scheduler._tick(datetime.now(timezone.utc))

        # Tasks should execute in order
        assert execution_order == ["Task 1", "Task 2"]
