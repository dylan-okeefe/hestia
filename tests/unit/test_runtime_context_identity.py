"""Tests for runtime identity ContextVar lifecycle in the orchestrator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message
from hestia.orchestrator.engine import Orchestrator
from hestia.runtime_context import current_platform, current_platform_user


@pytest.fixture
def mock_deps():
    """Minimal mocked dependencies for Orchestrator."""
    inference = MagicMock()
    session_store = MagicMock()
    context_builder = MagicMock()
    tool_registry = MagicMock()
    policy = MagicMock()
    failure_store = MagicMock()

    context_builder.build = AsyncMock(return_value=[{"role": "system", "content": "sys"}])
    inference.chat = AsyncMock(
        return_value=MagicMock(
            content="hello",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )
    )

    session_store.insert_turn = AsyncMock()
    session_store.update_turn = AsyncMock()
    session_store.append_transition = AsyncMock()
    session_store.append_message = AsyncMock()
    session_store.get_messages = AsyncMock(return_value=[])

    policy.filter_tools = MagicMock(return_value=[])
    policy.turn_token_budget = MagicMock(return_value=8000)
    policy.should_compress = MagicMock(return_value=False)

    return {
        "inference": inference,
        "session_store": session_store,
        "context_builder": context_builder,
        "tool_registry": tool_registry,
        "policy": policy,
        "failure_store": failure_store,
    }


@pytest.mark.asyncio
async def test_context_vars_set_during_success(mock_deps):
    """Identity ContextVars are set during process_turn and reset after success."""
    from datetime import datetime

    from hestia.core.types import Session, SessionState, SessionTemperature

    session = Session(
        id="sess_1",
        platform="telegram",
        platform_user="123456789",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    # Verify pre-state
    assert current_platform.get() is None
    assert current_platform_user.get() is None

    # Patch context_builder.build to assert vars are set mid-flight
    original_build = mock_deps["context_builder"].build

    async def _build_with_assertion(*args, **kwargs):
        assert current_platform.get() == "telegram"
        assert current_platform_user.get() == "123456789"
        return await original_build(*args, **kwargs)

    mock_deps["context_builder"].build = _build_with_assertion

    orchestrator = Orchestrator(
        inference=mock_deps["inference"],
        session_store=mock_deps["session_store"],
        context_builder=mock_deps["context_builder"],
        tool_registry=mock_deps["tool_registry"],
        policy=mock_deps["policy"],
    )

    await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="hi"),
        respond_callback=AsyncMock(),
    )

    # Verify post-state is reset
    assert current_platform.get() is None
    assert current_platform_user.get() is None


@pytest.mark.asyncio
async def test_context_vars_reset_on_failure(mock_deps):
    """Identity ContextVars are reset even when process_turn fails internally."""
    from datetime import datetime

    from hestia.core.types import Session, SessionState, SessionTemperature
    from hestia.orchestrator.types import TurnState

    session = Session(
        id="sess_2",
        platform="matrix",
        platform_user="@user:matrix.org",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    mock_deps["context_builder"].build = AsyncMock(side_effect=RuntimeError("boom"))

    orchestrator = Orchestrator(
        inference=mock_deps["inference"],
        session_store=mock_deps["session_store"],
        context_builder=mock_deps["context_builder"],
        tool_registry=mock_deps["tool_registry"],
        policy=mock_deps["policy"],
        failure_store=mock_deps["failure_store"],
    )

    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="hi"),
        respond_callback=AsyncMock(),
    )

    # Orchestrator catches the error and returns a failed turn
    assert turn.state == TurnState.FAILED
    assert turn.error == "boom"

    # Verify post-state is reset even after internal failure
    assert current_platform.get() is None
    assert current_platform_user.get() is None


@pytest.mark.asyncio
async def test_context_vars_set_from_session_not_kwargs(mock_deps):
    """ContextVars are driven by session fields, not optional kwargs."""
    from datetime import datetime

    from hestia.core.types import Session, SessionState, SessionTemperature

    session = Session(
        id="sess_3",
        platform="cli",
        platform_user="default",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    async def _build_with_assertion(*args, **kwargs):
        assert current_platform.get() == "cli"
        assert current_platform_user.get() == "default"
        return [{"role": "system", "content": "sys"}]

    mock_deps["context_builder"].build = _build_with_assertion

    orchestrator = Orchestrator(
        inference=mock_deps["inference"],
        session_store=mock_deps["session_store"],
        context_builder=mock_deps["context_builder"],
        tool_registry=mock_deps["tool_registry"],
        policy=mock_deps["policy"],
    )

    await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="hi"),
        respond_callback=AsyncMock(),
        platform=None,  # optional kwarg should not affect ContextVar
        platform_user=None,
    )

    assert current_platform.get() is None
    assert current_platform_user.get() is None
