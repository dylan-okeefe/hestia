"""Regression tests for artifact handle accumulation from ToolCallResult."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import ChatResponse, Message, ToolCall
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.types import TurnState
from hestia.tools.types import ToolCallResult


@pytest.mark.asyncio
async def test_artifact_handle_accumulated_in_trace():
    """A tool returning an artifact_handle populates the trace record."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()
    mock_trace_store = MagicMock()

    mock_policy.auto_approve.return_value = True
    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    mock_inference.chat = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                reasoning_content=None,
                tool_calls=[
                    ToolCall(id="tc1", name="generate_image", arguments={"prompt": "cat"})
                ],
                finish_reason="tool_calls",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            ChatResponse(
                content="Here is your image.",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        ]
    )

    mock_context_builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    mock_tool_registry.list_names.return_value = ["generate_image"]
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.describe.return_value = MagicMock(
        requires_confirmation=False, capabilities=[]
    )
    mock_tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="[image generated]",
            artifact_handle="artifact://abc123",
            truncated=False,
        )
    )

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
        trace_store=mock_trace_store,
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

    with patch.object(orchestrator, "_create_turn", return_value=mock_turn):
        with patch.object(orchestrator, "_persist_turn", AsyncMock()):
            turn = await orchestrator.process_turn(
                session=mock_session,
                user_message=Message(role="user", content="Draw a cat."),
                respond_callback=AsyncMock(),
            )

    assert turn.state == TurnState.DONE
    mock_trace_store.record.assert_called_once()
    trace = mock_trace_store.record.call_args[0][0]
    assert trace.artifact_handles == ["artifact://abc123"]


def test_no_regex_artifact_recovery_in_process_turn():
    """The regex-based artifact:// recovery path must be gone from process_turn."""
    source = inspect.getsource(Orchestrator.process_turn)
    assert "re.findall" not in source
    assert 'artifact://([a-zA-Z0-9_-]+)' not in source
