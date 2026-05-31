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


@pytest.mark.asyncio
async def test_streaming_thinking_budget_abort_retries():
    """Excessive thinking chunks abort the stream and trigger a retry with nudge."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    # Budget of 10 tokens => 40 chars before abort
    mock_policy.reasoning_budget.return_value = 10

    async def _stream_excessive_thinking(*args, **kwargs):
        # Each chunk is 15 chars => 2 chunks = 30 chars (within 40)
        # 3 chunks = 45 chars (> 40) => abort on 3rd chunk
        yield StreamDelta(content="", reasoning_content="thinking " * 5)  # 45 chars
        yield StreamDelta(content="", reasoning_content="more " * 5)  # would exceed
        yield StreamDelta(content="never reached")

    async def _stream_retry(*args, **kwargs):
        yield StreamDelta(content="Done after nudge")
        yield StreamDelta(content="", finish_reason="stop")

    mock_inference.chat_stream = MagicMock(
        side_effect=[_stream_excessive_thinking(), _stream_retry()]
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

    transition = AsyncMock()
    result = await execution.run(ctx, transition, AsyncMock())
    assert result == "Done after nudge"
    assert turn.thinking_aborted is True
    assert turn.iterations == 1

    # Verify transition to RETRYING happened
    transition.assert_any_call(turn, TurnState.RETRYING, "")

    # Verify nudge was appended to session store and running history
    assert len(mock_session_store.append_message.await_args_list) >= 1
    nudge_call = mock_session_store.append_message.await_args_list[0]
    nudge_msg = nudge_call.args[1]
    assert nudge_msg.role == "system"
    assert "Stop deliberating" in nudge_msg.content

    # Verify second chat_stream call had reasoning_budget=0
    second_call = mock_inference.chat_stream.call_args_list[1]
    assert second_call.kwargs["reasoning_budget"] == 0


@pytest.mark.asyncio
async def test_streaming_thinking_within_budget_completes():
    """Reasoning content within budget allows normal completion."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    # Budget of 100 tokens => 400 chars
    mock_policy.reasoning_budget.return_value = 100

    async def _stream(*args, **kwargs):
        yield StreamDelta(content="", reasoning_content="short reasoning")
        yield StreamDelta(content="Hello")
        yield StreamDelta(content="", finish_reason="stop")

    mock_inference.chat_stream = MagicMock(return_value=_stream())
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
    assert result == "Hello"
    assert turn.thinking_aborted is False
    assert turn.iterations == 0


@pytest.mark.asyncio
async def test_streaming_thinking_abort_limit_enforced():
    """Only one thinking-abort per turn: pre-flagged turn ignores budget."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    # Budget of 1 token => 4 chars, but turn is already flagged
    mock_policy.reasoning_budget.return_value = 1

    async def _stream(*args, **kwargs):
        # 50 chars of reasoning > 4 char budget, but abort is skipped
        yield StreamDelta(content="", reasoning_content="x" * 50)
        yield StreamDelta(content="Completed")
        yield StreamDelta(content="", finish_reason="stop")

    mock_inference.chat_stream = MagicMock(return_value=_stream())
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
        thinking_aborted=True,
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
    assert result == "Completed"
    assert turn.thinking_aborted is True
    assert turn.iterations == 0
    # reasoning_budget should have been forced to 0 at loop top
    mock_inference.chat_stream.assert_called_once()
    call_kwargs = mock_inference.chat_stream.call_args.kwargs
    assert call_kwargs["reasoning_budget"] == 0
