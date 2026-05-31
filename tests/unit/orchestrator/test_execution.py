"""Unit tests for TurnExecution direct tool dispatch (L161)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature, ToolCall
from hestia.errors import MaxIterationsError
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.types import Turn, TurnContext, TurnState
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolRegistry
from hestia.tools.types import ToolCallResult


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
async def test_direct_write_file_dispatch():
    """A direct write_file tool call is dispatched correctly."""
    registry = ToolRegistry(MagicMock())
    async def _write_file(**kwargs: object) -> str:
        return "Wrote file"

    registry._tools["write_file"] = ToolMetadata(
        name="write_file",
        public_description="Write a file",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=_write_file,
    )

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    tc = ToolCall(
        id="tc1", name="write_file", arguments={"path": "/tmp/test.txt", "content": "hi"}
    )
    result = await execution._dispatch_tool_call(_make_session(), tc)
    assert result.status == "ok"
    assert "Wrote file" in result.content


def test_call_tool_not_in_dispatch_table():
    """call_tool is no longer in the meta-tool dispatch table."""
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )
    # The _meta_tools attribute was removed entirely in L161.
    assert not hasattr(execution, "_meta_tools")


@pytest.mark.asyncio
async def test_max_iterations_error_raised(make_chat_response):
    """Canned ChatResponse sequences that exceed max_iterations raise MaxIterationsError."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
        max_iterations=2,
    )

    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            finish_reason="tool_calls",
            tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={})],
        )
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    with patch.object(
        execution, "_handle_tool_calls", new_callable=AsyncMock
    ) as mock_handle:
        # _handle_tool_calls increments iterations and continues the loop
        async def _side_effect(*args, **kwargs):
            ctx.turn.iterations += 1
            return TurnState.BUILDING_CONTEXT

        mock_handle.side_effect = _side_effect

        with pytest.raises(MaxIterationsError) as exc_info:
            await execution.run(ctx, AsyncMock(), AsyncMock())

        assert exc_info.value.max_iterations == 2


@pytest.mark.asyncio
async def test_per_turn_tool_call_cap_enforced():
    """Per-turn tool-call cap exceeded: cap enforced, excess calls get errors."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        max_tool_calls_per_turn=2,
    )

    tool_calls = [
        ToolCall(id="tc1", name="tool_a", arguments={}),
        ToolCall(id="tc2", name="tool_b", arguments={}),
        ToolCall(id="tc3", name="tool_c", arguments={}),
        ToolCall(id="tc4", name="tool_d", arguments={}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="ok",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls
        )

        # Only first 2 should have been dispatched
        assert mock_dispatch.call_count == 2
        dispatched_names = [call.args[1].name for call in mock_dispatch.call_args_list]
        assert dispatched_names == ["tool_a", "tool_b"]

        # 4 result messages total: 2 cap-rejection errors + 2 real results
        assert len(result_messages) == 4
        assert "too many tool calls" in result_messages[0].content
        assert "too many tool calls" in result_messages[1].content
        assert result_messages[0].tool_call_id == "tc3"
        assert result_messages[1].tool_call_id == "tc4"
        assert result_messages[2].content == "ok"
        assert result_messages[3].content == "ok"
        assert artifact_handles == []


@pytest.mark.asyncio
async def test_tool_result_truncated_before_reprompting():
    """A 50 KB tool result is clipped before being added to result messages."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 100

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    huge_content = "x" * 50_000
    tool_calls = [
        ToolCall(id="tc1", name="big_tool", arguments={}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content=huge_content,
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls
        )

        assert len(result_messages) == 1
        msg = result_messages[0]
        assert len(msg.content) < len(huge_content)
        assert msg.content.endswith("\n... [truncated]")
        assert msg.content.startswith("x" * 100)
        policy.tool_result_max_chars.assert_called_once_with("big_tool")
