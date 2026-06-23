"""Unit tests for L221 §5 — Degenerate tool-call turn."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.errors import PolicyFailureError
from hestia.orchestrator.execution import (
    _MAX_DEGENERATE_TOOL_CALL_RETRIES,
    TurnExecution,
)
from hestia.orchestrator.types import Turn, TurnContext, TurnState


def _make_session() -> Session:
    return Session(
        id="test-session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


def _make_turn() -> Turn:
    return Turn(
        id="turn-1",
        session_id="test-session",
        state=TurnState.RECEIVED,
        user_message=Message(role="user", content="hello"),
        started_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_empty_tool_call_batch_does_not_append_message(make_chat_response):
    """A degenerate tool-call turn does not persist an assistant message."""
    message_store = MagicMock()
    message_store.append_message = AsyncMock()

    inference_client = MagicMock()
    inference_client.chat = AsyncMock(
        return_value=make_chat_response(finish_reason="tool_calls", tool_calls=[])
    )

    policy = MagicMock()
    policy.reasoning_budget.return_value = 2048

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        message_store=message_store,
        max_iterations=10,
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    with pytest.raises(PolicyFailureError):
        await execution.run(ctx, AsyncMock(), AsyncMock())

    # No assistant message should have been persisted for the degenerate turns.
    assert message_store.append_message.await_count == 0


@pytest.mark.asyncio
async def test_degenerate_tool_call_turn_retries_and_fails(make_chat_response):
    """Degenerate tool-call turns retry up to the cap then fail."""
    message_store = MagicMock()
    message_store.append_message = AsyncMock()

    inference_client = MagicMock()
    inference_client.chat = AsyncMock(
        return_value=make_chat_response(finish_reason="tool_calls", tool_calls=[])
    )

    policy = MagicMock()
    policy.reasoning_budget.return_value = 2048

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        message_store=message_store,
        max_iterations=10,
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    with pytest.raises(PolicyFailureError) as exc_info:
        await execution.run(ctx, AsyncMock(), AsyncMock())

    assert "finish_reason='tool_calls'" in str(exc_info.value)
    assert "giving up" in str(exc_info.value).lower()

    # The model should have been called for each allowed retry plus the final
    # failing attempt. Iterations advance only on non-failing retries.
    max_retries = _MAX_DEGENERATE_TOOL_CALL_RETRIES
    assert inference_client.chat.await_count == max_retries + 1
    assert ctx._degenerate_tool_call_retries == max_retries + 1
    assert ctx.turn.iterations == max_retries
