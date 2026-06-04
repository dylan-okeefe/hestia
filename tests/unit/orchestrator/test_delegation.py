"""Tests for parent-context inheritance in policy delegation."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, ToolCall
from hestia.orchestrator.execution import TurnExecution


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


@pytest.mark.asyncio
async def test_execute_policy_delegation_passes_task_and_context(
    execution: TurnExecution,
) -> None:
    """delegate_task receives task and context in its arguments."""
    user_message = Message(role="user", content="do it", created_at=datetime.now())
    tool_calls = [ToolCall(id="tc1", name="some_tool", arguments={})]

    execution._tools.call = AsyncMock(
        return_value=MagicMock(
            status="ok",
            content="delegated",
            artifact_handle=None,
            truncated=False,
        )
    )

    await execution._execute_policy_delegation(user_message, tool_calls)

    call_args = execution._tools.call.await_args
    assert call_args is not None
    args = call_args[0]
    assert args[0] == "delegate_task"
    assert "task" in args[1]
    assert args[1]["task"] == "do it"
    assert "context" in args[1]
