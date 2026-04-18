"""Integration tests for reflection scheduler behavior."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from hestia.config import ReflectionConfig
from hestia.core.clock import utcnow
from hestia.core.types import ChatResponse, Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.persistence.trace_store import TraceStore
from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.scheduler import ReflectionScheduler
from hestia.reflection.store import ProposalStore


class FakeInference:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    async def count_request(self, messages, tools=None):
        return 10

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return ChatResponse(
            content='{"observations": [], "proposals": []}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        pass


@pytest.fixture
async def db(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.connect()
    await db.create_tables()
    yield db
    await db.close()


@pytest.fixture
async def session_store(db):
    return SessionStore(db)


@pytest.fixture
async def trace_store(db):
    store = TraceStore(db)
    await store.create_table()
    return store


@pytest.fixture
async def proposal_store(db):
    store = ProposalStore(db)
    await store.create_table()
    return store


class TestReflectionScheduler:
    async def test_runs_during_idle(self, db, session_store, trace_store, proposal_store):
        """Scheduler runs reflection when no session has been active recently."""
        config = ReflectionConfig(
            enabled=True,
            cron="* * * * *",  # every minute
            idle_minutes=15,
            lookback_turns=10,
            proposals_per_run=5,
            expire_days=14,
        )

        inference = FakeInference()
        runner = ReflectionRunner(
            config=config,
            inference=inference,
            trace_store=trace_store,
            proposal_store=proposal_store,
        )
        scheduler = ReflectionScheduler(
            config=config,
            runner=runner,
            session_store=session_store,
        )

        now = utcnow()
        proposals = await scheduler.tick(now)
        # No traces, so no proposals expected
        assert proposals == []

    async def test_skips_when_session_recently_active(
        self, db, session_store, trace_store, proposal_store
    ):
        """Scheduler skips reflection when a session was active within idle_minutes."""
        config = ReflectionConfig(
            enabled=True,
            cron="* * * * *",
            idle_minutes=15,
            lookback_turns=10,
            proposals_per_run=5,
            expire_days=14,
        )

        # Create an active session with recent last_active_at
        now = utcnow()
        session = Session(
            id="sess_001",
            platform="cli",
            platform_user="test",
            started_at=now - timedelta(minutes=5),
            last_active_at=now - timedelta(minutes=5),
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.HOT,
        )
        # Insert directly via session store's db
        import sqlalchemy as sa
        from hestia.persistence.schema import sessions

        async with db.engine.connect() as conn:
            await conn.execute(
                sa.insert(sessions).values(
                    id=session.id,
                    platform=session.platform,
                    platform_user=session.platform_user,
                    started_at=session.started_at,
                    last_active_at=session.last_active_at,
                    slot_id=session.slot_id,
                    slot_saved_path=session.slot_saved_path,
                    state=session.state.value,
                    temperature=session.temperature.value,
                )
            )
            await conn.commit()

        inference = FakeInference()
        runner = ReflectionRunner(
            config=config,
            inference=inference,
            trace_store=trace_store,
            proposal_store=proposal_store,
        )
        scheduler = ReflectionScheduler(
            config=config,
            runner=runner,
            session_store=session_store,
        )

        proposals = await scheduler.tick(now)
        assert proposals == []
        # Inference should not have been called
        assert inference.call_count == 0

    async def test_no_proposals_under_low_signal(self, db, session_store, trace_store, proposal_store):
        """When traces exist but model returns no observations, no proposals are generated."""
        config = ReflectionConfig(
            enabled=True,
            cron="* * * * *",
            idle_minutes=0,
            lookback_turns=10,
            proposals_per_run=5,
            expire_days=14,
        )

        # Add a trace
        from hestia.persistence.trace_store import TraceRecord

        await trace_store.record(
            TraceRecord(
                id="tr1",
                session_id="s1",
                turn_id="turn_1",
                started_at=utcnow(),
                ended_at=utcnow(),
                user_input_summary="Hello",
                tools_called=[],
                tool_call_count=0,
                delegated=False,
                outcome="success",
                artifact_handles=[],
                prompt_tokens=10,
                completion_tokens=5,
                reasoning_tokens=0,
                total_duration_ms=1000,
            )
        )

        inference = FakeInference(
            responses=[
                ChatResponse(
                    content='{"observations": []}',
                    reasoning_content=None,
                    tool_calls=[],
                    finish_reason="stop",
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
            ]
        )
        runner = ReflectionRunner(
            config=config,
            inference=inference,
            trace_store=trace_store,
            proposal_store=proposal_store,
        )
        scheduler = ReflectionScheduler(
            config=config,
            runner=runner,
            session_store=session_store,
        )

        proposals = await scheduler.tick(utcnow())
        assert proposals == []
