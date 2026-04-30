"""Unit tests for Orchestrator rate limiting integration."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.rate_limiter import SessionRateLimiter
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.errors import PlatformError
from hestia.orchestrator.engine import Orchestrator


@pytest.fixture
def base_orchestrator():
    orch = Orchestrator(
        inference=MagicMock(),
        session_store=MagicMock(),
        context_builder=MagicMock(),
        tool_registry=MagicMock(),
        policy=MagicMock(),
    )
    orch._persist_turn = AsyncMock()
    orch._set_typing = AsyncMock()
    orch._assembly = MagicMock()
    orch._assembly.prepare = AsyncMock()
    orch._execution = MagicMock()
    orch._execution.run = AsyncMock()
    orch._finalization = MagicMock()
    orch._finalization.finalize_turn = AsyncMock()
    return orch


@pytest.fixture
def sample_session():
    return Session(
        id="s1",
        platform="cli",
        platform_user="default",
        started_at=__import__("datetime").datetime.now(),
        last_active_at=__import__("datetime").datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_exceeded(base_orchestrator, sample_session):
    limiter = SessionRateLimiter(rate=0.1, capacity=1.0)
    base_orchestrator._rate_limiter = limiter

    # First turn consumes the single token
    respond = AsyncMock()
    await base_orchestrator.process_turn(
        session=sample_session,
        user_message=Message(role="user", content="hi"),
        respond_callback=respond,
    )
    assert respond.call_count == 0  # Normal flow, no rate limit response

    # Second turn should be blocked
    respond2 = AsyncMock()
    with pytest.raises(PlatformError, match="Rate limit exceeded"):
        await base_orchestrator.process_turn(
            session=sample_session,
            user_message=Message(role="user", content="hi again"),
            respond_callback=respond2,
        )
    respond2.assert_awaited_once()
    assert "Rate limit exceeded" in respond2.call_args[0][0]


@pytest.mark.asyncio
async def test_rate_limiter_disabled_when_none(base_orchestrator, sample_session):
    base_orchestrator._rate_limiter = None
    base_orchestrator._create_turn = MagicMock(return_value=MagicMock())
    base_orchestrator._persist_turn = AsyncMock()
    base_orchestrator._set_typing = AsyncMock()
    base_orchestrator._assembly = MagicMock()
    base_orchestrator._assembly.prepare = AsyncMock()
    base_orchestrator._execution = MagicMock()
    base_orchestrator._execution.run = AsyncMock()
    base_orchestrator._finalization = MagicMock()
    base_orchestrator._finalization.finalize_turn = AsyncMock()

    respond = AsyncMock()
    # Should not raise even with many calls
    for _ in range(5):
        await base_orchestrator.process_turn(
            session=sample_session,
            user_message=Message(role="user", content="hi"),
            respond_callback=respond,
        )
