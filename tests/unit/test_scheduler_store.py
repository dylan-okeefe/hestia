"""Unit tests for SchedulerStore."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from hestia.errors import PersistenceError
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore, _calculate_next_run
from hestia.persistence.sessions import SessionStore


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


class TestCalculateNextRun:
    """Tests for the _calculate_next_run helper function."""

    def test_fire_at_future(self):
        """fire_at in future returns the fire_at time."""
        future = datetime.now(UTC) + timedelta(hours=1)
        result = _calculate_next_run(None, future)
        assert result == future

    def test_fire_at_past_returns_created_at(self):
        """fire_at in past returns created_at (run immediately)."""
        past = datetime.now(UTC) - timedelta(hours=1)
        created = datetime.now(UTC) - timedelta(minutes=5)
        result = _calculate_next_run(None, past, created_at=created)
        assert result == created

    def test_cron_expression_calculates_next(self):
        """cron_expression calculates next occurrence from base time."""
        base = datetime(2024, 1, 1, 12, 0, 0)  # Noon
        # Every day at 9 AM - next should be tomorrow at 9 AM
        result = _calculate_next_run("0 9 * * *", None, base)
        assert result == datetime(2024, 1, 2, 9, 0, 0)

    def test_cron_expression_same_day(self):
        """cron_expression returns same day if before trigger time."""
        base = datetime(2024, 1, 1, 8, 0, 0)  # 8 AM
        # Every day at 9 AM - next should be today at 9 AM
        result = _calculate_next_run("0 9 * * *", None, base)
        assert result == datetime(2024, 1, 1, 9, 0, 0)

    def test_invalid_cron_raises_error(self):
        """Invalid cron expression raises PersistenceError."""
        with pytest.raises(PersistenceError, match="Invalid cron expression"):
            _calculate_next_run("invalid", None)

    def test_both_none_returns_none(self):
        """Both arguments None returns None."""
        result = _calculate_next_run(None, None)
        assert result is None


class TestCreateTask:
    """Tests for create_task method."""

    @pytest.mark.asyncio
    async def test_create_cron_task(self, scheduler_store, test_session):
        """Can create a recurring task with cron expression."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Daily summary",
            description="Run every day",
            cron_expression="0 9 * * *",
        )

        assert task.session_id == test_session.id
        assert task.prompt == "Daily summary"
        assert task.description == "Run every day"
        assert task.cron_expression == "0 9 * * *"
        assert task.fire_at is None
        assert task.enabled is True
        assert task.next_run_at is not None  # Should be calculated
        assert task.last_run_at is None
        assert task.last_error is None
        assert task.id.startswith("task_")

    @pytest.mark.asyncio
    async def test_create_fire_at_task(self, scheduler_store, test_session):
        """Can create a one-time task with fire_at."""
        fire_at = datetime.now() + timedelta(days=1)
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="One-time task",
            fire_at=fire_at,
        )

        assert task.cron_expression is None
        assert task.fire_at == fire_at
        assert task.next_run_at == fire_at

    @pytest.mark.asyncio
    async def test_create_requires_exactly_one_schedule(self, scheduler_store, test_session):
        """Must provide exactly one of cron_expression or fire_at."""
        fire_at = datetime.now() + timedelta(days=1)

        # Both provided
        with pytest.raises(PersistenceError, match="Cannot specify both"):
            await scheduler_store.create_task(
                session_id=test_session.id,
                prompt="Test",
                cron_expression="0 9 * * *",
                fire_at=fire_at,
            )

        # Neither provided
        with pytest.raises(PersistenceError, match="Must specify either"):
            await scheduler_store.create_task(
                session_id=test_session.id,
                prompt="Test",
            )

    @pytest.mark.asyncio
    async def test_create_disabled_task(self, scheduler_store, test_session):
        """Can create a disabled task."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Disabled task",
            cron_expression="0 9 * * *",
            enabled=False,
        )

        assert task.enabled is False


class TestListDueTasks:
    """Tests for list_due_tasks method."""

    @pytest.mark.asyncio
    async def test_list_due_tasks_excludes_future(self, scheduler_store, test_session):
        """Tasks with future next_run_at are not returned."""
        future = datetime.now() + timedelta(days=1)
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Future task",
            fire_at=future,
        )

        due = await scheduler_store.list_due_tasks()
        assert len(due) == 0

    @pytest.mark.asyncio
    async def test_list_due_tasks_includes_past(self, scheduler_store, test_session):
        """Tasks with past fire_at are returned as due (run immediately semantics)."""
        past = datetime.now() - timedelta(seconds=1)  # Just barely in the past
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Past task",
            fire_at=past,
        )

        due = await scheduler_store.list_due_tasks()
        assert len(due) == 1
        assert due[0].prompt == "Past task"

    @pytest.mark.asyncio
    async def test_list_due_tasks_excludes_disabled(self, scheduler_store, test_session):
        """Disabled tasks are not returned."""
        past = datetime.now() - timedelta(hours=1)
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Disabled task",
            fire_at=past,
            enabled=False,
        )

        due = await scheduler_store.list_due_tasks()
        assert len(due) == 0

    @pytest.mark.asyncio
    async def test_list_due_tasks_respects_limit(self, scheduler_store, test_session):
        """Limit parameter controls number of results."""
        past = datetime.now() - timedelta(hours=1)
        for i in range(5):
            await scheduler_store.create_task(
                session_id=test_session.id,
                prompt=f"Task {i}",
                fire_at=past + timedelta(minutes=i),
            )

        due = await scheduler_store.list_due_tasks(limit=3)
        assert len(due) == 3


class TestUpdateAfterRun:
    """Tests for update_after_run method."""

    @pytest.mark.asyncio
    async def test_update_cron_calculates_next_run(self, scheduler_store, test_session):
        """After successful cron task run, next_run_at is recalculated."""
        datetime(2024, 1, 1, 8, 0, 0)
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Daily task",
            cron_expression="0 9 * * *",  # 9 AM daily
        )

        # Simulate running at 9 AM
        run_time = datetime(2024, 1, 1, 9, 0, 0)
        updated = await scheduler_store.update_after_run(task.id, now=run_time)

        assert updated.last_run_at == run_time
        assert updated.next_run_at == datetime(2024, 1, 2, 9, 0, 0)  # Tomorrow
        assert updated.enabled is True  # Cron tasks stay enabled
        assert updated.last_error is None

    @pytest.mark.asyncio
    async def test_update_one_time_disables_on_success(self, scheduler_store, test_session):
        """After successful one-time task run, task is disabled."""
        fire_at = datetime.now() - timedelta(hours=1)
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="One-time task",
            fire_at=fire_at,
        )

        updated = await scheduler_store.update_after_run(task.id)

        assert updated.enabled is False
        assert updated.next_run_at is None

    @pytest.mark.asyncio
    async def test_update_preserves_enabled_on_error(self, scheduler_store, test_session):
        """On error, one-time task stays enabled for retry."""
        fire_at = datetime.now() - timedelta(hours=1)
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="One-time task",
            fire_at=fire_at,
        )

        updated = await scheduler_store.update_after_run(task.id, error="Connection failed")

        assert updated.enabled is True  # Stay enabled for retry
        assert updated.last_error == "Connection failed"

    @pytest.mark.asyncio
    async def test_update_returns_none_for_missing_task(self, scheduler_store):
        """Returns None if task not found."""
        result = await scheduler_store.update_after_run("task_nonexistent")
        assert result is None


class TestListTasksForSession:
    """Tests for list_tasks_for_session method."""

    @pytest.mark.asyncio
    async def test_list_tasks_filters_by_session(self, scheduler_store, session_store):
        """Only returns tasks for specified session."""
        session1 = await session_store.get_or_create_session("test", "user1")
        session2 = await session_store.get_or_create_session("test", "user2")

        await scheduler_store.create_task(
            session_id=session1.id,
            prompt="Task for session 1",
            cron_expression="0 9 * * *",
        )
        await scheduler_store.create_task(
            session_id=session2.id,
            prompt="Task for session 2",
            cron_expression="0 10 * * *",
        )

        tasks = await scheduler_store.list_tasks_for_session(session1.id)
        assert len(tasks) == 1
        assert tasks[0].prompt == "Task for session 1"

    @pytest.mark.asyncio
    async def test_list_tasks_excludes_disabled_by_default(self, scheduler_store, test_session):
        """By default, disabled tasks are excluded."""
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Enabled task",
            cron_expression="0 9 * * *",
        )
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Disabled task",
            cron_expression="0 10 * * *",
            enabled=False,
        )

        tasks = await scheduler_store.list_tasks_for_session(test_session.id)
        assert len(tasks) == 1
        assert tasks[0].prompt == "Enabled task"

    @pytest.mark.asyncio
    async def test_list_tasks_includes_disabled_when_requested(self, scheduler_store, test_session):
        """Can include disabled tasks with include_disabled=True."""
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Enabled task",
            cron_expression="0 9 * * *",
        )
        await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Disabled task",
            cron_expression="0 10 * * *",
            enabled=False,
        )

        tasks = await scheduler_store.list_tasks_for_session(test_session.id, include_disabled=True)
        assert len(tasks) == 2


class TestDisableTask:
    """Tests for disable_task method."""

    @pytest.mark.asyncio
    async def test_disable_existing_task(self, scheduler_store, test_session):
        """Can disable an existing task."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Task to disable",
            cron_expression="0 9 * * *",
        )

        result = await scheduler_store.disable_task(task.id)
        assert result is True

        fetched = await scheduler_store.get_task(task.id)
        assert fetched.enabled is False

    @pytest.mark.asyncio
    async def test_disable_missing_task(self, scheduler_store):
        """Returns False for non-existent task."""
        result = await scheduler_store.disable_task("task_nonexistent")
        assert result is False


class TestGetTask:
    """Tests for get_task method."""

    @pytest.mark.asyncio
    async def test_get_existing_task(self, scheduler_store, test_session):
        """Can retrieve existing task."""
        created = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Test task",
            cron_expression="0 9 * * *",
        )

        fetched = await scheduler_store.get_task(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.prompt == "Test task"

    @pytest.mark.asyncio
    async def test_get_missing_task(self, scheduler_store):
        """Returns None for non-existent task."""
        result = await scheduler_store.get_task("task_nonexistent")
        assert result is None


class TestSetEnabled:
    """Tests for set_enabled method."""

    @pytest.mark.asyncio
    async def test_enable_disabled_task(self, scheduler_store, test_session):
        """Can re-enable a disabled task."""
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Test",
            cron_expression="0 9 * * *",
            enabled=False,
        )
        result = await scheduler_store.set_enabled(task.id, True)
        assert result is True
        fetched = await scheduler_store.get_task(task.id)
        assert fetched.enabled is True

    @pytest.mark.asyncio
    async def test_set_enabled_missing_task(self, scheduler_store):
        result = await scheduler_store.set_enabled("task_nonexistent", True)
        assert result is False


class TestDeleteTask:
    """Tests for delete_task method."""

    @pytest.mark.asyncio
    async def test_delete_existing_task(self, scheduler_store, test_session):
        task = await scheduler_store.create_task(
            session_id=test_session.id,
            prompt="Delete me",
            cron_expression="0 9 * * *",
        )
        result = await scheduler_store.delete_task(task.id)
        assert result is True
        fetched = await scheduler_store.get_task(task.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_missing_task(self, scheduler_store):
        result = await scheduler_store.delete_task("task_nonexistent")
        assert result is False


class TestRowToTask:
    """Tests for _row_to_task coercion."""

    def test_null_enabled_defaults_to_false(self, scheduler_store):
        """A row with NULL enabled must coerce to False, not None."""
        from datetime import datetime
        from types import SimpleNamespace

        row = SimpleNamespace(
            id="task_001",
            session_id="sess_001",
            prompt="test",
            description=None,
            cron_expression="0 0 * * *",
            fire_at=None,
            enabled=None,
            created_at=datetime.now(UTC),
            last_run_at=None,
            next_run_at=None,
            last_error=None,
        )
        task = scheduler_store._row_to_task(row)
        assert task.enabled is False

    def test_null_created_at_defaults_to_now(self, scheduler_store):
        """A row with NULL created_at must default to utcnow()."""
        from datetime import datetime
        from types import SimpleNamespace

        before = datetime.now(UTC)
        row = SimpleNamespace(
            id="task_002",
            session_id="sess_001",
            prompt="test",
            description=None,
            cron_expression="0 0 * * *",
            fire_at=None,
            enabled=True,
            created_at=None,
            last_run_at=None,
            next_run_at=None,
            last_error=None,
        )
        task = scheduler_store._row_to_task(row)
        after = datetime.now(UTC)
        assert before <= task.created_at <= after
