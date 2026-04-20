"""Tests for scheduler preserving creator identity through runtime context."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from hestia.core.types import Message, ScheduledTask, Session
from hestia.orchestrator.types import Turn, TurnState
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.runtime_context import current_platform, current_platform_user
from hestia.scheduler import Scheduler


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


class IdentityCapturingOrchestrator:
    """Orchestrator that simulates real ContextVar behavior during process_turn."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.captured_platforms: list[str | None] = []
        self.captured_platform_users: list[str | None] = []

    async def process_turn(
        self,
        session: Session,
        user_message: Message,
        respond_callback: AsyncMock,
    ) -> Turn:
        # Simulate what the real Orchestrator does: set ContextVars from session
        platform_token = current_platform.set(session.platform)
        platform_user_token = current_platform_user.set(session.platform_user)
        try:
            # Capture ContextVars as seen inside process_turn
            self.captured_platforms.append(current_platform.get())
            self.captured_platform_users.append(current_platform_user.get())
            self.calls.append({"session": session, "user_message": user_message})
            await respond_callback("Done")
            return Turn(
                id="turn_1",
                session_id=session.id,
                state=TurnState.DONE,
                user_message=user_message,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                iterations=1,
                tool_calls_made=0,
                final_response="Done",
                error=None,
                transitions=[],
            )
        finally:
            current_platform.reset(platform_token)
            current_platform_user.reset(platform_user_token)


@pytest.mark.asyncio
async def test_scheduler_preserves_creator_identity(
    scheduler_store, session_store
):
    """Scheduler task execution carries creator platform:platform_user identity."""
    session = await session_store.get_or_create_session("telegram", "123456789")
    task = await scheduler_store.create_task(
        session_id=session.id,
        prompt="Daily reminder",
        cron_expression="0 9 * * *",
    )

    orchestrator = IdentityCapturingOrchestrator()
    responses: list[dict] = []

    async def response_callback(task: ScheduledTask, text: str) -> None:
        responses.append({"task": task, "text": text})

    scheduler = Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=orchestrator,
        response_callback=response_callback,
        tick_interval_seconds=5.0,
    )

    run_time = datetime.now(timezone.utc)
    await scheduler._fire_task(task, run_time)

    # Verify orchestrator saw the creator identity
    assert len(orchestrator.calls) == 1
    assert orchestrator.captured_platforms == ["telegram"]
    assert orchestrator.captured_platform_users == ["123456789"]

    # Verify ContextVars are cleaned up after scheduler tick
    assert current_platform.get() is None
    assert current_platform_user.get() is None


@pytest.mark.asyncio
async def test_scheduler_identity_on_failure(scheduler_store, session_store):
    """ContextVars are reset even when scheduler task raises inside process_turn."""
    session = await session_store.get_or_create_session("matrix", "@owner:matrix.org")
    task = await scheduler_store.create_task(
        session_id=session.id,
        prompt="Failing task",
        fire_at=datetime.now(timezone.utc),
    )

    class FailingOrchestrator:
        async def process_turn(self, session, user_message, respond_callback):
            # Simulate real Orchestrator: set vars, then fail
            platform_token = current_platform.set(session.platform)
            platform_user_token = current_platform_user.set(session.platform_user)
            try:
                assert current_platform.get() == "matrix"
                assert current_platform_user.get() == "@owner:matrix.org"
                raise RuntimeError("intentional failure")
            finally:
                current_platform.reset(platform_token)
                current_platform_user.reset(platform_user_token)

    scheduler = Scheduler(
        scheduler_store=scheduler_store,
        session_store=session_store,
        orchestrator=FailingOrchestrator(),
        response_callback=AsyncMock(),
        tick_interval_seconds=5.0,
    )

    await scheduler._fire_task(task, datetime.now(timezone.utc))

    # Verify ContextVars are cleaned up after failure
    assert current_platform.get() is None
    assert current_platform_user.get() is None
