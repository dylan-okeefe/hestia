"""Tests for scheduler + Matrix delivery and policy enforcement."""

# mypy: disable-error-code="no-untyped-def,arg-type"
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio

from hestia.core.types import Message, ScheduledTask, Session
from hestia.orchestrator.types import Turn, TurnState
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.scheduler import Scheduler


class FakeMatrixAdapter:
    """Fake Matrix adapter that captures sent messages."""

    def __init__(self):
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(self, user: str, text: str) -> str:
        self.sent_messages.append({"user": user, "text": text})
        return "$event123"


class FakeOrchestrator:
    """Fake orchestrator for testing scheduler."""

    def __init__(self, responses: list[str] | None = None, should_fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = responses or ["Task completed"]
        self.should_fail = should_fail
        self.turn_error: str | None = None

    async def process_turn(
        self,
        session: Session,
        user_message: Message,
        respond_callback: Any,
        **kwargs: Any,
    ) -> Turn:
        self.calls.append(
            {
                "session": session,
                "user_message": user_message,
            }
        )

        if self.should_fail:
            raise RuntimeError("Orchestrator failed")

        for response in self.responses:
            await respond_callback(response)

        return Turn(
            id="turn_123",
            session_id=session.id,
            state=TurnState.DONE,
            user_message=user_message,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            iterations=1,
            tool_calls_made=0,
            final_response=self.responses[-1],
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
async def matrix_session(session_store):
    """Create a matrix platform session."""
    return await session_store.get_or_create_session("matrix", "!test-room:matrix.org")


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


class TestSchedulerMatrixDelivery:
    """Tests for scheduler delivering to Matrix sessions."""

    @pytest.mark.asyncio
    async def test_one_shot_delivers_to_matrix_room(
        self, scheduler_store, session_store, matrix_session
    ):
        """One-shot task bound to a Matrix session delivers to the room."""
        adapter = FakeMatrixAdapter()
        response_log = []

        async def matrix_callback(task: ScheduledTask, text: str) -> None:
            response_log.append({"task": task, "text": text})
            session = await session_store.get_session(task.session_id)
            if session and session.platform == "matrix":
                await adapter.send_message(session.platform_user, text)

        fire_at = datetime.now(UTC) - timedelta(minutes=5)
        task = await scheduler_store.create_task(
            session_id=matrix_session.id,
            prompt="Hello from scheduler",
            fire_at=fire_at,
        )

        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=FakeOrchestrator(responses=["Scheduled hello"]),
            response_callback=matrix_callback,
            tick_interval_seconds=5.0,
        )

        await scheduler._fire_task(task, datetime.now(UTC))

        # Verify response was captured
        assert len(response_log) == 1
        assert response_log[0]["text"] == "Scheduled hello"

        # Verify Matrix adapter received the message
        assert len(adapter.sent_messages) == 1
        assert adapter.sent_messages[0]["user"] == "!test-room:matrix.org"
        assert adapter.sent_messages[0]["text"] == "Scheduled hello"

    @pytest.mark.asyncio
    async def test_cron_task_advances_next_run(
        self, scheduler_store, session_store, matrix_session
    ):
        """Cron task fires and advances next_run_at; does not disable."""
        base_time = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)

        task = await scheduler_store.create_task(
            session_id=matrix_session.id,
            prompt="Cron hello",
            cron_expression="*/5 * * * *",  # every 5 minutes
        )
        # Override next_run_at to be due at base_time
        await scheduler_store.update_after_run(
            task.id, error=None, now=base_time, next_run_at=base_time
        )

        scheduler = await make_scheduler(
            scheduler_store, session_store, [], FakeOrchestrator(), tick_interval=5.0
        )

        await scheduler._fire_task(task, base_time)

        updated = await scheduler_store.get_task(task.id)
        assert updated.enabled is True
        assert updated.next_run_at == datetime(2024, 1, 1, 9, 5, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_scheduler_skips_delivery_when_session_not_matrix(
        self, scheduler_store, session_store
    ):
        """Matrix scheduler callback skips if session platform is not matrix."""
        cli_session = await session_store.get_or_create_session("cli", "default")
        adapter = FakeMatrixAdapter()
        response_log = []

        async def matrix_callback(task: ScheduledTask, text: str) -> None:
            response_log.append({"task": task, "text": text})
            session = await session_store.get_session(task.session_id)
            if session and session.platform == "matrix":
                await adapter.send_message(session.platform_user, text)

        fire_at = datetime.now(UTC) - timedelta(minutes=5)
        task = await scheduler_store.create_task(
            session_id=cli_session.id,
            prompt="CLI task",
            fire_at=fire_at,
        )

        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=FakeOrchestrator(responses=["CLI response"]),
            response_callback=matrix_callback,
            tick_interval_seconds=5.0,
        )

        await scheduler._fire_task(task, datetime.now(UTC))

        # Response captured but not delivered to Matrix
        assert len(response_log) == 1
        assert len(adapter.sent_messages) == 0


class TestSchedulerPolicy:
    """Tests for policy enforcement during scheduler ticks."""

    @pytest.mark.asyncio
    async def test_scheduler_tick_records_error_for_denied_tool(
        self, scheduler_store, session_store, matrix_session
    ):
        """When a destructive tool is denied, scheduler tick records the error."""
        # Fake orchestrator that simulates a turn where a denied tool produces an error
        orch = FakeOrchestrator()
        orch.turn_error = "Tool write_file was denied: no confirm_callback is configured"

        fire_at = datetime.now(UTC) - timedelta(minutes=5)
        task = await scheduler_store.create_task(
            session_id=matrix_session.id,
            prompt="Write a file please",
            fire_at=fire_at,
        )

        scheduler = await make_scheduler(scheduler_store, session_store, [], orch)
        await scheduler._fire_task(task, datetime.now(UTC))

        updated = await scheduler_store.get_task(task.id)
        assert "denied" in updated.last_error.lower() or "confirm_callback" in updated.last_error

    @pytest.mark.asyncio
    async def test_scheduler_tick_sets_scheduler_tick_active_flag(
        self, scheduler_store, session_store, matrix_session
    ):
        """Scheduler tick sets scheduler_tick_active context variable."""
        from hestia.runtime_context import scheduler_tick_active

        recorded_flag = None

        class ObservingOrchestrator(FakeOrchestrator):
            async def process_turn(self, session, user_message, respond_callback, **kwargs):
                nonlocal recorded_flag
                recorded_flag = scheduler_tick_active.get()
                return await super().process_turn(
                    session, user_message, respond_callback, **kwargs
                )

        fire_at = datetime.now(UTC) - timedelta(minutes=5)
        task = await scheduler_store.create_task(
            session_id=matrix_session.id,
            prompt="Observed task",
            fire_at=fire_at,
        )

        scheduler = await make_scheduler(
            scheduler_store, session_store, [], ObservingOrchestrator()
        )
        await scheduler._fire_task(task, datetime.now(UTC))

        assert recorded_flag is True


class TestSchedulerTeardown:
    """Tests for task cleanup after tests."""

    @pytest.mark.asyncio
    async def test_task_can_be_deleted_after_run(
        self, scheduler_store, session_store, matrix_session
    ):
        """Tasks can be removed via scheduler_store.delete_task."""
        fire_at = datetime.now(UTC) - timedelta(minutes=5)
        task = await scheduler_store.create_task(
            session_id=matrix_session.id,
            prompt="Temporary task",
            fire_at=fire_at,
        )

        # Run and then delete
        scheduler = await make_scheduler(scheduler_store, session_store, [], FakeOrchestrator())
        await scheduler._fire_task(task, datetime.now(UTC))

        success = await scheduler_store.delete_task(task.id)
        assert success is True

        assert await scheduler_store.get_task(task.id) is None
