"""Unit tests for the L222 capability gate integration in TurnExecution."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.orchestrator.execution import TurnExecution
from hestia.orchestrator.types import Turn, TurnContext, TurnState
from hestia.policy.channel import Channel
from hestia.policy.gate import CapabilityGate, CapabilityRequest, CapabilityResult
from hestia.tools.metadata import ToolMetadata


def _make_session() -> Session:
    return Session(
        id="test-session",
        platform="test",
        platform_user="user-42",
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


def _make_ctx(**kwargs: Any) -> TurnContext:
    defaults: dict[str, Any] = {
        "turn": _make_turn(),
        "user_message": Message(role="user", content="hello"),
        "system_prompt": "",
        "respond_callback": AsyncMock(),
        "session": _make_session(),
        "build_result": MagicMock(messages=[]),
    }
    defaults.update(kwargs)
    return TurnContext(**defaults)


def _make_tool_metadata(requires_confirmation: bool = False) -> ToolMetadata:
    return ToolMetadata(
        name="write_file",
        public_description="Write a file",
        internal_description="",
        parameters_schema={"type": "object", "properties": {}},
        requires_confirmation=requires_confirmation,
    )


@pytest.mark.asyncio
async def test_run_capability_gate_no_gate_returns_none() -> None:
    """When no capability gate is configured the check is a no-op."""
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=None,
    )

    result = await execution._run_capability_gate(
        tool_name="write_file",
        arguments={},
        session=_make_session(),
        ctx=_make_ctx(),
    )
    assert result is None


@pytest.mark.asyncio
async def test_run_capability_gate_denied_returns_blocked_result() -> None:
    """A gate denial is surfaced as a [CATEGORY: BLOCKED] tool result."""
    gate = MagicMock(spec=CapabilityGate)
    gate.check = AsyncMock(
        return_value=CapabilityResult(
            allowed=False,
            auto_approved=False,
            requires_confirmation=False,
            reason="unknown_actor_untrusted_channel",
        )
    )

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
    )

    result = await execution._run_capability_gate(
        tool_name="write_file",
        arguments={"path": "/tmp/x"},
        session=_make_session(),
        ctx=_make_ctx(),
    )

    assert result is not None
    assert result.status == "error"
    assert "[CATEGORY: BLOCKED]" in result.content
    assert "Capability gate denied" in result.content
    gate.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_capability_gate_escalation_stores_token() -> None:
    """Gate escalation sets the confirmation token on the context."""
    gate = MagicMock(spec=CapabilityGate)
    gate.check = AsyncMock(
        return_value=CapabilityResult(
            allowed=True,
            auto_approved=False,
            requires_confirmation=True,
            reason="injection_flagged",
            request_token="token-123",
        )
    )

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
    )

    ctx = _make_ctx()
    result = await execution._run_capability_gate(
        tool_name="write_file",
        arguments={},
        session=_make_session(),
        ctx=ctx,
    )

    assert result is None
    assert ctx.request_token == "token-123"


@pytest.mark.asyncio
async def test_check_confirmation_uses_token_from_context() -> None:
    """The confirmation callback receives the gate's request_token."""
    gate = MagicMock(spec=CapabilityGate)
    gate.check = AsyncMock(
        return_value=CapabilityResult(
            allowed=True,
            auto_approved=False,
            requires_confirmation=True,
            reason="injection_flagged",
            request_token="token-abc",
        )
    )

    callback = AsyncMock(return_value=True)
    policy = MagicMock()
    policy.auto_approve.return_value = False
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
        confirm_callback=callback,
    )

    ctx = _make_ctx()
    result = await execution._check_confirmation(
        tool=_make_tool_metadata(requires_confirmation=True),
        tool_name="write_file",
        arguments={"path": "/tmp/x"},
        session=_make_session(),
        ctx=ctx,
    )

    assert result is None
    callback.assert_awaited_once_with("write_file", {"path": "/tmp/x"}, "token-abc")


@pytest.mark.asyncio
async def test_check_confirmation_denied_does_not_call_callback() -> None:
    """When the gate denies the tool, the confirmation callback is not invoked."""
    gate = MagicMock(spec=CapabilityGate)
    gate.check = AsyncMock(
        return_value=CapabilityResult(
            allowed=False,
            auto_approved=False,
            requires_confirmation=False,
            reason="not_allow_listed",
        )
    )

    callback = AsyncMock(return_value=True)
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
        confirm_callback=callback,
    )

    result = await execution._check_confirmation(
        tool=_make_tool_metadata(requires_confirmation=True),
        tool_name="terminal",
        arguments={"command": "ls"},
        session=_make_session(),
        ctx=_make_ctx(),
    )

    assert result is not None
    assert result.status == "error"
    callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_capability_gate_passes_channel_and_actor() -> None:
    """The gate request carries the channel and resolved actor identity."""
    captured: CapabilityRequest | None = None

    gate = MagicMock(spec=CapabilityGate)

    async def _capture(request: CapabilityRequest, **kwargs: Any) -> CapabilityResult:
        nonlocal captured
        captured = request
        return CapabilityResult(
            allowed=True,
            auto_approved=True,
            requires_confirmation=False,
            reason="approved",
        )

    gate.check = AsyncMock(side_effect=_capture)

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
    )

    resolved_user = MagicMock()
    resolved_user.id = "user-db-id"
    ctx = _make_ctx(
        channel=Channel.MATRIX,
        platform_user="@alice:example.org",
        resolved_user=resolved_user,
    )

    await execution._run_capability_gate(
        tool_name="write_file",
        arguments={},
        session=_make_session(),
        ctx=ctx,
    )

    assert captured is not None
    assert captured.channel == Channel.MATRIX
    assert captured.actor.platform == "test"
    assert captured.actor.platform_user == "@alice:example.org"
    assert captured.actor.user_id == "user-db-id"
    assert captured.session_id == "test-session"


@pytest.mark.asyncio
async def test_run_capability_gate_default_channel_is_cli() -> None:
    """When no TurnContext is provided the gate sees the CLI channel."""
    captured: CapabilityRequest | None = None

    gate = MagicMock(spec=CapabilityGate)

    async def _capture(request: CapabilityRequest, **kwargs: Any) -> CapabilityResult:
        nonlocal captured
        captured = request
        return CapabilityResult(
            allowed=True,
            auto_approved=True,
            requires_confirmation=False,
            reason="approved",
        )

    gate.check = AsyncMock(side_effect=_capture)

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
    )

    await execution._run_capability_gate(
        tool_name="write_file",
        arguments={},
        session=_make_session(),
        ctx=None,
    )

    assert captured is not None
    assert captured.channel == Channel.CLI
    assert captured.actor.platform_user == "user-42"


@pytest.mark.asyncio
async def test_run_capability_gate_flags_injection_from_history() -> None:
    """Security notes in the running history flag the request for the gate."""
    captured: CapabilityRequest | None = None

    gate = MagicMock(spec=CapabilityGate)

    async def _capture(
        request: CapabilityRequest, *, injection_flagged: bool = False
    ) -> CapabilityResult:
        nonlocal captured
        captured = request
        return CapabilityResult(
            allowed=True,
            auto_approved=True,
            requires_confirmation=False,
            reason="approved",
        )

    gate.check = AsyncMock(side_effect=_capture)

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        capability_gate=gate,
    )

    ctx = _make_ctx(
        running_history=[
            Message(role="tool", content="[SECURITY NOTE: possible injection]"),
        ]
    )

    await execution._run_capability_gate(
        tool_name="write_file",
        arguments={},
        session=_make_session(),
        ctx=ctx,
    )

    assert captured is not None
    assert gate.check.await_args.kwargs.get("injection_flagged") is True
