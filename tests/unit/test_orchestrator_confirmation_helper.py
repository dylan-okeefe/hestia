"""Regression tests for the _check_confirmation helper."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.orchestrator.execution import TurnExecution
from hestia.tools.metadata import ToolMetadata
from hestia.tools.types import ToolCallResult


def _make_turn_execution(*, confirm_callback=None, auto_approve=False):
    mock_policy = MagicMock()
    mock_policy.auto_approve.return_value = auto_approve

    return TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=mock_policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        confirm_callback=confirm_callback,
    )


@pytest.mark.asyncio
async def test_no_confirmation_required():
    """Tool without requires_confirmation returns None immediately."""
    turn_execution = _make_turn_execution()
    tool = ToolMetadata(
        name="safe_tool",
        public_description="A safe tool",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
    )

    result = await turn_execution._check_confirmation(
        tool=tool, tool_name="safe_tool", arguments={}, session=MagicMock()
    )
    assert result is None


@pytest.mark.asyncio
async def test_confirmed_returns_none():
    """When confirm_callback approves, _check_confirmation returns None."""
    confirm_callback = AsyncMock(return_value=True)
    turn_execution = _make_turn_execution(confirm_callback=confirm_callback)
    tool = ToolMetadata(
        name="risky_tool",
        public_description="A risky tool",
        internal_description="",
        parameters_schema={},
        requires_confirmation=True,
    )

    result = await turn_execution._check_confirmation(
        tool=tool,
        tool_name="risky_tool",
        arguments={"command": "rm -rf /"},
        session=MagicMock(),
    )
    assert result is None
    confirm_callback.assert_awaited_once_with("risky_tool", {"command": "rm -rf /"})


@pytest.mark.asyncio
async def test_denied_returns_error_result():
    """When confirm_callback denies, _check_confirmation returns ToolCallResult.error."""
    confirm_callback = AsyncMock(return_value=False)
    turn_execution = _make_turn_execution(confirm_callback=confirm_callback)
    tool = ToolMetadata(
        name="risky_tool",
        public_description="A risky tool",
        internal_description="",
        parameters_schema={},
        requires_confirmation=True,
    )

    result = await turn_execution._check_confirmation(
        tool=tool,
        tool_name="risky_tool",
        arguments={"command": "rm -rf /"},
        session=MagicMock(),
    )
    assert result is not None
    assert isinstance(result, ToolCallResult)
    assert result.status == "error"
    assert "cancelled by user" in result.content
    assert result.artifact_handle is None
    assert result.truncated is False


@pytest.mark.asyncio
async def test_no_callback_returns_error_result():
    """When no confirm_callback is configured, _check_confirmation returns ToolCallResult.error."""
    turn_execution = _make_turn_execution(confirm_callback=None)
    tool = ToolMetadata(
        name="risky_tool",
        public_description="A risky tool",
        internal_description="",
        parameters_schema={},
        requires_confirmation=True,
    )

    result = await turn_execution._check_confirmation(
        tool=tool,
        tool_name="risky_tool",
        arguments={"command": "rm -rf /"},
        session=MagicMock(),
    )
    assert result is not None
    assert isinstance(result, ToolCallResult)
    assert result.status == "error"
    assert "confirm_callback is configured" in result.content
    assert result.artifact_handle is None
    assert result.truncated is False


@pytest.mark.asyncio
async def test_auto_approve_skips_callback():
    """When policy auto-approves, callback is not consulted."""
    confirm_callback = AsyncMock(return_value=True)
    turn_execution = _make_turn_execution(
        confirm_callback=confirm_callback, auto_approve=True
    )
    tool = ToolMetadata(
        name="risky_tool",
        public_description="A risky tool",
        internal_description="",
        parameters_schema={},
        requires_confirmation=True,
    )

    result = await turn_execution._check_confirmation(
        tool=tool,
        tool_name="risky_tool",
        arguments={"command": "rm -rf /"},
        session=MagicMock(),
    )
    assert result is None
    confirm_callback.assert_not_awaited()
