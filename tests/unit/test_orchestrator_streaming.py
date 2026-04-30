"""Tests for orchestrator streaming path."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from hestia.core.types import (
    Message,
    Session,
    SessionState,
    SessionTemperature,
    StreamDelta,
)
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.types import Turn, TurnContext, TurnState
from hestia.tools.types import ToolCallResult


@pytest.mark.asyncio
async def test_streaming_path_content_chunks():
    """When stream=True and stream_callback is set, content chunks are streamed."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    async def _stream(*args, **kwargs):
        yield StreamDelta(content="Hello")
        yield StreamDelta(content=" world")
        yield StreamDelta(
            content="",
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    mock_inference.chat_stream = MagicMock(return_value=_stream())
    mock_policy.reasoning_budget.return_value = 2048
    mock_session_store.append_message = AsyncMock()

    execution = TurnExecution(
        tool_registry=mock_tool_registry,
        inference_client=mock_inference,
        policy=mock_policy,
        context_builder=mock_context_builder,
        session_store=mock_session_store,
        stream=True,
    )

    stream_callback = AsyncMock()
    turn = Turn(
        id="test-turn",
        session_id="test-session",
        state=TurnState.RECEIVED,
        user_message=Message(role="user", content="hi"),
        started_at=datetime.now(),
    )
    session = Session(
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
    ctx = TurnContext(
        turn=turn,
        user_message=Message(role="user", content="hi"),
        system_prompt="You are helpful.",
        respond_callback=AsyncMock(),
        session=session,
        build_result=MagicMock(messages=[]),
        stream_callback=stream_callback,
    )

    result = await execution.run(ctx, AsyncMock(), AsyncMock())
    assert result == "Hello world"
    stream_callback.assert_has_calls([call("Hello"), call(" world")])
    assert ctx.total_prompt_tokens == 10
    assert ctx.total_completion_tokens == 5
    mock_inference.chat.assert_not_called()


@pytest.mark.asyncio
async def test_non_streaming_path_unchanged():
    """When stream=False, the non-streaming chat() path is used."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    from hestia.core.types import ChatResponse

    mock_inference.chat = AsyncMock(
        return_value=ChatResponse(
            content="Hello!",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    mock_context_builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.list_names.return_value = []

    mock_session_store.insert_turn = AsyncMock()
    mock_session_store.update_turn = AsyncMock()
    mock_session_store.append_transition = AsyncMock()
    mock_session_store.append_message = AsyncMock()
    mock_session_store.get_messages = AsyncMock(return_value=[])

    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        stream=False,
    )

    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.slot_id = None

    mock_turn = MagicMock()
    mock_turn.id = "test-turn-id"
    mock_turn.iterations = 0
    mock_turn.tool_calls_made = 0
    mock_turn.transitions = []
    mock_turn.state = TurnState.RECEIVED

    with (
        patch.object(orchestrator, "_create_turn", return_value=mock_turn),
        patch.object(orchestrator, "_persist_turn", AsyncMock()),
    ):
        await orchestrator.process_turn(
            session=mock_session,
            user_message=Message(role="user", content="hi"),
            respond_callback=AsyncMock(),
        )

    mock_inference.chat.assert_awaited_once()
    mock_inference.chat_stream.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_tool_call_accumulation():
    """Tool call chunks are accumulated by index during streaming."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    async def _stream_tool_calls(*args, **kwargs):
        yield StreamDelta(
            content="",
            tool_call_chunks=[
                {
                    "index": 0,
                    "id": "tc1",
                    "function": {"name": "terminal", "arguments": '{"command": "'},
                }
            ],
        )
        yield StreamDelta(
            content="",
            tool_call_chunks=[
                {"index": 0, "function": {"arguments": 'echo hi"}'}}
            ],
        )
        yield StreamDelta(content="", finish_reason="tool_calls")

    async def _stream_final(*args, **kwargs):
        yield StreamDelta(content="Done!")
        yield StreamDelta(content="", finish_reason="stop")

    mock_inference.chat_stream = MagicMock(
        side_effect=[_stream_tool_calls(), _stream_final()]
    )

    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.should_delegate.return_value = False

    mock_tool_registry.list_names.return_value = ["terminal"]
    mock_tool_registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="parallel"
    )
    mock_tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok", content="hi", artifact_handle=None, truncated=False
        )
    )

    mock_session_store.append_message = AsyncMock()
    mock_context_builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    execution = TurnExecution(
        tool_registry=mock_tool_registry,
        inference_client=mock_inference,
        policy=mock_policy,
        context_builder=mock_context_builder,
        session_store=mock_session_store,
        stream=True,
    )

    stream_callback = AsyncMock()
    turn = Turn(
        id="test-turn",
        session_id="test-session",
        state=TurnState.RECEIVED,
        user_message=Message(role="user", content="run terminal"),
        started_at=datetime.now(),
    )
    session = Session(
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
    ctx = TurnContext(
        turn=turn,
        user_message=Message(role="user", content="run terminal"),
        system_prompt="You are helpful.",
        respond_callback=AsyncMock(),
        session=session,
        build_result=MagicMock(messages=[]),
        stream_callback=stream_callback,
    )

    result = await execution.run(ctx, AsyncMock(), AsyncMock())
    assert result == "Done!"
    assert turn.tool_calls_made == 1

    # Verify the tool was called with accumulated arguments
    mock_tool_registry.call.assert_awaited_once_with("terminal", {"command": "echo hi"})

    # stream_callback should have been called for the final content chunk
    stream_callback.assert_called_once_with("Done!")
