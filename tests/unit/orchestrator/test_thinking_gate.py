"""Tests for per-chat gating of the reasoning display in TurnExecution (L250)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import (
    Message,
    Session,
    SessionState,
    SessionTemperature,
    StreamDelta,
    ToolCall,
)
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.types import Turn, TurnContext, TurnState


def _make_session(platform: str = "telegram", platform_user: str = "90001") -> Session:
    return Session(
        id="test-session",
        platform=platform,
        platform_user=platform_user,
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


def _make_execution(reasoning_gate, stream: bool = False) -> TurnExecution:
    message_store = MagicMock()
    message_store.append_message = AsyncMock()
    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    return TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=builder,
        session_store=MagicMock(),
        message_store=message_store,
        reasoning_gate=reasoning_gate,
        stream=stream,
    )


def _patch_execute(execution: TurnExecution):
    """Patch _execute_tool_calls on an execution instance."""
    return patch.object(
        execution, "_execute_tool_calls", new_callable=AsyncMock, return_value=([], [])
    )


def _prep_policy(execution: TurnExecution) -> None:
    execution._policy.filter_tools.return_value = []
    execution._policy.reasoning_budget.return_value = 2048
    execution._policy.turn_token_budget.return_value = 40000


def _make_ctx(respond_callback: AsyncMock) -> TurnContext:
    return TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=respond_callback,
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )


_REASONING = "Let me think about this carefully."


# --- Final-answer display path (non-streaming) ---


@pytest.mark.asyncio
async def test_no_gate_shows_reasoning_as_before(make_chat_response):
    """Without a gate, reasoning is prepended (historical behavior)."""
    execution = _make_execution(None)
    _prep_policy(execution)
    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            content="answer", reasoning_content=_REASONING
        )
    )

    respond = AsyncMock()
    await execution.run(_make_ctx(respond), AsyncMock(), AsyncMock())

    display = respond.await_args.args[0]
    assert "💭" in display
    assert _REASONING in display
    assert "answer" in display


@pytest.mark.asyncio
async def test_gate_hidden_suppresses_reasoning_display(make_chat_response):
    """Gate returning False: the user sees only the final answer."""
    gate = AsyncMock(return_value=False)
    execution = _make_execution(gate)
    _prep_policy(execution)
    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            content="answer", reasoning_content=_REASONING
        )
    )

    respond = AsyncMock()
    await execution.run(_make_ctx(respond), AsyncMock(), AsyncMock())

    gate.assert_awaited_once_with("telegram", "90001")
    display = respond.await_args.args[0]
    assert "💭" not in display
    assert _REASONING not in display
    assert display == "answer"


@pytest.mark.asyncio
async def test_gate_shown_keeps_reasoning_display(make_chat_response):
    """Gate returning True: reasoning is prepended as usual."""
    gate = AsyncMock(return_value=True)
    execution = _make_execution(gate)
    _prep_policy(execution)
    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            content="answer", reasoning_content=_REASONING
        )
    )

    respond = AsyncMock()
    await execution.run(_make_ctx(respond), AsyncMock(), AsyncMock())

    display = respond.await_args.args[0]
    assert "💭" in display


@pytest.mark.asyncio
async def test_gate_failure_falls_back_to_showing(make_chat_response):
    """A broken gate must not fail the turn; display defaults to showing."""
    gate = AsyncMock(side_effect=RuntimeError("db exploded"))
    execution = _make_execution(gate)
    _prep_policy(execution)
    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            content="answer", reasoning_content=_REASONING
        )
    )

    respond = AsyncMock()
    state = await execution.run(_make_ctx(respond), AsyncMock(), AsyncMock())

    assert state == "answer"
    assert "💭" in respond.await_args.args[0]


# --- Tool-execution display path ---


@pytest.mark.asyncio
async def test_tool_call_reasoning_hidden_by_gate():
    """The pre-tool 💭 message is suppressed when the gate says hide."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )
    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )
    execution._builder.build = AsyncMock()
    execution._message_store.append_message = AsyncMock()
    execution._policy.should_delegate = MagicMock(return_value=False)

    respond = AsyncMock()
    ctx = _make_ctx(respond)

    chat_response = MagicMock()
    chat_response.content = ""
    chat_response.reasoning_content = _REASONING
    chat_response.tool_calls = [
        ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/x"})
    ]

    with _patch_execute(execution):
        await execution._handle_tool_calls(
            ctx,
            _make_turn(),
            chat_response,
            AsyncMock(),
            AsyncMock(),
            MagicMock(),
            show_reasoning=False,
        )

    sent = [c.args[0] for c in respond.await_args_list]
    assert all("💭" not in text for text in sent)


@pytest.mark.asyncio
async def test_tool_call_reasoning_shown_without_gate():
    """Default (no show_reasoning arg) keeps the pre-tool 💭 message."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )
    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )
    execution._builder.build = AsyncMock()
    execution._message_store.append_message = AsyncMock()
    execution._policy.should_delegate = MagicMock(return_value=False)

    respond = AsyncMock()
    ctx = _make_ctx(respond)

    chat_response = MagicMock()
    chat_response.content = ""
    chat_response.reasoning_content = _REASONING
    chat_response.tool_calls = [
        ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/x"})
    ]

    with _patch_execute(execution):
        await execution._handle_tool_calls(
            ctx,
            _make_turn(),
            chat_response,
            AsyncMock(),
            AsyncMock(),
            MagicMock(),
        )

    sent = [c.args[0] for c in respond.await_args_list]
    assert any("💭" in text and _REASONING in text for text in sent)


# --- Streaming path ---


@pytest.mark.asyncio
async def test_streaming_reasoning_display_gated(make_chat_response):
    """Streaming turns: accumulated reasoning stays internal when hidden.

    reasoning_parts must still accumulate (the transcript and the tool-call
    XML fallback need it) but the post-stream display must not include 💭.
    """
    gate = AsyncMock(return_value=False)
    execution = _make_execution(gate, stream=True)
    _prep_policy(execution)

    async def fake_stream(**kwargs):
        yield StreamDelta(content="", reasoning_content="thinking…")
        yield StreamDelta(content="streamed answer")
        yield StreamDelta(content="", reasoning_content="more thinking")
        yield StreamDelta(content="", finish_reason="stop")

    execution._inference.chat_stream = fake_stream

    respond = AsyncMock()
    stream_chunks: list[str] = []

    async def stream_callback(chunk: str) -> None:
        stream_chunks.append(chunk)

    ctx = _make_ctx(respond)
    ctx.stream_callback = stream_callback

    await execution.run(ctx, AsyncMock(), AsyncMock())

    # Stream delivered only content, no reasoning.
    assert stream_chunks == ["streamed answer"]
    # Final display has no 💭.
    display = respond.await_args.args[0]
    assert "💭" not in display
    assert "streamed answer" in display


