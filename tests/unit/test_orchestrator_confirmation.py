"""Tests for orchestrator confirmation gate with auto_approve."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import (
    ChatResponse,
    Message,
    Session,
    SessionState,
    SessionTemperature,
    ToolCall,
)
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.types import TurnState
from hestia.tools.types import ToolCallResult


def _make_session(platform: str = "test") -> Session:
    from datetime import datetime

    return Session(
        id="test-session",
        platform=platform,
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


@pytest.mark.asyncio
async def test_refuses_without_auto_approve_and_no_callback():
    """A tool requiring confirmation is refused when policy doesn't auto-approve
    and no confirm_callback is configured."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    mock_policy.auto_approve.return_value = False
    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048

    # Simulate model asking for terminal (requires_confirmation=True)
    mock_inference.chat = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                reasoning_content=None,
                tool_calls=[
                    ToolCall(id="tc1", name="terminal", arguments={"command": "echo hi"})
                ],
                finish_reason="tool_calls",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            ChatResponse(
                content="I cannot run that command.",
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

    mock_tool_registry.list_names.return_value = ["terminal"]
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.describe.return_value = MagicMock(
        requires_confirmation=True, capabilities=["shell_exec"]
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
        confirm_callback=None,
    )

    session = _make_session()
    user_msg = Message(role="user", content="Run a command.")
    respond_callback = AsyncMock()

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_msg,
        respond_callback=respond_callback,
    )

    assert turn.state == TurnState.DONE
    # The tool result message should contain the rejection reason
    calls = mock_session_store.append_message.call_args_list
    tool_msgs = []
    for c in calls:
        msg = c.kwargs.get("message") or c.args[1] if len(c.args) > 1 else c.args[0]
        if hasattr(msg, "role") and msg.role == "tool":
            tool_msgs.append(msg)
    assert any("trust profile does not auto-approve" in m.content for m in tool_msgs)


@pytest.mark.asyncio
async def test_auto_approves_without_callback():
    """A tool requiring confirmation runs when policy auto-approves it,
    even without a confirm_callback."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    mock_policy.auto_approve.return_value = True
    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048

    mock_inference.chat = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                reasoning_content=None,
                tool_calls=[
                    ToolCall(id="tc1", name="terminal", arguments={"command": "echo hi"})
                ],
                finish_reason="tool_calls",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            ChatResponse(
                content="Done!",
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

    mock_tool_registry.list_names.return_value = ["terminal"]
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.describe.return_value = MagicMock(
        requires_confirmation=True, capabilities=["shell_exec"]
    )
    mock_tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok", content="hi", artifact_handle=None, truncated=False
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
        confirm_callback=None,
    )

    session = _make_session()
    user_msg = Message(role="user", content="Run a command.")
    respond_callback = AsyncMock()

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_msg,
        respond_callback=respond_callback,
    )

    assert turn.state == TurnState.DONE
    # The tool should have been called via the registry
    mock_tool_registry.call.assert_awaited_once_with("terminal", {"command": "echo hi"})


@pytest.mark.asyncio
async def test_uses_callback_when_present():
    """When confirm_callback is present, it is used regardless of auto-approve state."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    mock_policy.auto_approve.return_value = False
    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048

    mock_inference.chat = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                reasoning_content=None,
                tool_calls=[
                    ToolCall(id="tc1", name="terminal", arguments={"command": "echo hi"})
                ],
                finish_reason="tool_calls",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            ChatResponse(
                content="Cancelled.",
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

    mock_tool_registry.list_names.return_value = ["terminal"]
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.describe.return_value = MagicMock(
        requires_confirmation=True, capabilities=["shell_exec"]
    )

    mock_session_store.insert_turn = AsyncMock()
    mock_session_store.update_turn = AsyncMock()
    mock_session_store.append_transition = AsyncMock()
    mock_session_store.append_message = AsyncMock()
    mock_session_store.get_messages = AsyncMock(return_value=[])

    confirm_callback = AsyncMock(return_value=False)  # User denies

    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        confirm_callback=confirm_callback,
    )

    session = _make_session()
    user_msg = Message(role="user", content="Run a command.")
    respond_callback = AsyncMock()

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_msg,
        respond_callback=respond_callback,
    )

    assert turn.state == TurnState.DONE
    # The callback should have been consulted when auto_approve is False
    confirm_callback.assert_awaited_once_with("terminal", {"command": "echo hi"})
