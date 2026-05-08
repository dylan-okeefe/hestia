"""Tests for parent-context inheritance in policy delegation."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, ToolCall
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.types import TurnContext


@pytest.fixture
def execution() -> TurnExecution:
    """Minimal TurnExecution with mocked dependencies."""
    mock_registry = MagicMock()
    mock_inference = MagicMock()
    mock_policy = MagicMock()
    mock_builder = MagicMock()
    mock_store = MagicMock()
    return TurnExecution(
        tool_registry=mock_registry,
        inference_client=mock_inference,
        policy=mock_policy,
        context_builder=mock_builder,
        session_store=mock_store,
    )


def test_build_parent_context_empty_history(execution: TurnExecution) -> None:
    """Empty history returns an empty string."""
    assert execution._build_parent_context([]) == ""


def test_build_parent_context_includes_only_last_n(execution: TurnExecution) -> None:
    """Only the last N messages are included."""
    history = [
        Message(role="user", content=f"msg {i}", created_at=datetime.now())
        for i in range(15)
    ]
    result = execution._build_parent_context(history, max_messages=5)
    assert "msg 10" in result
    assert "msg 14" in result
    assert "msg 9" not in result
    assert "msg 0" not in result


def test_build_parent_context_truncates_long_tool_results(
    execution: TurnExecution,
) -> None:
    """Tool results longer than max_content_length are truncated."""
    long_content = "x" * 1000
    history = [
        Message(
            role="tool",
            content=long_content,
            tool_call_id="tc-1",
            created_at=datetime.now(),
        ),
    ]
    result = execution._build_parent_context(history, max_content_length=100)
    assert len(result) < len(long_content) + 50
    assert "...[truncated]" in result
    assert long_content[:100] in result


def test_build_parent_context_formats_roles(execution: TurnExecution) -> None:
    """Different message roles are formatted with appropriate prefixes."""
    history = [
        Message(role="user", content="hello", created_at=datetime.now()),
        Message(
            role="assistant",
            content="hi there",
            tool_calls=[ToolCall(id="c1", name="foo", arguments={"bar": 1})],
            created_at=datetime.now(),
        ),
        Message(
            role="tool",
            content="result",
            tool_call_id="c1",
            created_at=datetime.now(),
        ),
    ]
    result = execution._build_parent_context(history)
    assert "User: hello" in result
    assert "Assistant: hi there" in result
    assert "→ foo" in result
    assert "Tool (c1): result" in result


@pytest.mark.asyncio
async def test_execute_policy_delegation_passes_parent_context(
    execution: TurnExecution,
) -> None:
    """delegate_task receives parent_context in its arguments."""
    history = [
        Message(role="user", content="first thing", created_at=datetime.now()),
        Message(role="assistant", content="response", created_at=datetime.now()),
    ]
    mock_session = MagicMock()
    mock_session.id = "sess-1"
    turn = MagicMock()
    ctx = TurnContext(
        turn=turn,
        user_message=Message(role="user", content="do it", created_at=datetime.now()),
        system_prompt="sys",
        respond_callback=AsyncMock(),
        session=mock_session,
        running_history=history,
    )
    tool_calls = [ToolCall(id="tc1", name="some_tool", arguments={})]

    execution._tools.call = AsyncMock(
        return_value=MagicMock(
            status="ok",
            content="delegated",
            artifact_handle=None,
            truncated=False,
        )
    )

    await execution._execute_policy_delegation(ctx, tool_calls)

    call_args = execution._tools.call.await_args
    assert call_args is not None
    args = call_args[0]
    assert args[0] == "delegate_task"
    assert "parent_context" in args[1]
    assert "first thing" in args[1]["parent_context"]
    assert "response" in args[1]["parent_context"]
    assert args[1]["parent_context"] == execution._build_parent_context(history)
