"""Regression tests for failure bundle shape parity."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import Message
from hestia.errors import ContextTooLargeError
from hestia.orchestrator.engine import Orchestrator


@pytest.mark.asyncio
async def test_context_too_large_failure_bundle():
    """ContextTooLargeError path produces a FailureBundle with the right shape."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()
    mock_failure_store = MagicMock()

    mock_context_builder.build = AsyncMock(
        side_effect=ContextTooLargeError("protected context exceeds budget")
    )

    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.slot_id = 42
    mock_session.temperature.value = "hot"
    mock_session.slot_saved_path = "/tmp/slot.bin"

    mock_turn = MagicMock()
    mock_turn.id = "test-turn-id"
    mock_turn.iterations = 0
    mock_turn.tool_calls_made = 0
    mock_turn.transitions = []
    mock_turn.reasoning_budget = None

    mock_session_store.insert_turn = AsyncMock(return_value=None)
    mock_session_store.update_turn = AsyncMock(return_value=None)
    mock_session_store.append_transition = AsyncMock(return_value=None)
    mock_session_store.append_message = AsyncMock(return_value=None)
    mock_session_store.get_messages = AsyncMock(return_value=[])

    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        failure_store=mock_failure_store,
    )

    with (
        patch.object(orchestrator, "_create_turn", return_value=mock_turn),
        patch.object(orchestrator, "_persist_turn", AsyncMock()),
        patch.object(orchestrator, "_transition", AsyncMock()),
    ):
        user_message = Message(role="user", content="overflow me")
        respond_callback = AsyncMock()

        await orchestrator.process_turn(
            session=mock_session,
            user_message=user_message,
            respond_callback=respond_callback,
        )

    mock_failure_store.record.assert_called_once()
    bundle = mock_failure_store.record.call_args[0][0]

    assert bundle.failure_class == "context_overflow"
    assert bundle.severity == "medium"
    assert bundle.error_message == "protected context exceeds budget"
    assert bundle.session_id == "test-session-id"
    assert bundle.turn_id == "test-turn-id"
    assert bundle.request_summary is not None
    assert bundle.policy_snapshot is not None
    assert bundle.slot_snapshot is not None

    policy_data = json.loads(bundle.policy_snapshot)
    assert "reasoning_budget" in policy_data
    assert "turn_token_budget" in policy_data
    assert "tool_filter_active" in policy_data

    slot_data = json.loads(bundle.slot_snapshot)
    assert slot_data["slot_id"] == 42
    assert slot_data["temperature"] == "hot"
    assert slot_data["slot_saved_path"] == "/tmp/slot.bin"


@pytest.mark.asyncio
async def test_generic_exception_failure_bundle():
    """Generic Exception path produces a FailureBundle with the right shape."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()
    mock_failure_store = MagicMock()

    mock_context_builder.build = AsyncMock(side_effect=RuntimeError("something broke"))

    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.slot_id = 42
    mock_session.temperature.value = "hot"
    mock_session.slot_saved_path = "/tmp/slot.bin"

    mock_turn = MagicMock()
    mock_turn.id = "test-turn-id"
    mock_turn.iterations = 0
    mock_turn.tool_calls_made = 0
    mock_turn.transitions = []
    mock_turn.reasoning_budget = None

    mock_session_store.insert_turn = AsyncMock(return_value=None)
    mock_session_store.update_turn = AsyncMock(return_value=None)
    mock_session_store.append_transition = AsyncMock(return_value=None)
    mock_session_store.append_message = AsyncMock(return_value=None)
    mock_session_store.get_messages = AsyncMock(return_value=[])

    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        failure_store=mock_failure_store,
    )

    with (
        patch.object(orchestrator, "_create_turn", return_value=mock_turn),
        patch.object(orchestrator, "_persist_turn", AsyncMock()),
        patch.object(orchestrator, "_transition", AsyncMock()),
    ):
        user_message = Message(role="user", content="break me")
        respond_callback = AsyncMock()

        await orchestrator.process_turn(
            session=mock_session,
            user_message=user_message,
            respond_callback=respond_callback,
        )

    mock_failure_store.record.assert_called_once()
    bundle = mock_failure_store.record.call_args[0][0]

    assert bundle.failure_class == "unknown"
    assert bundle.severity == "medium"
    assert bundle.error_message == "something broke"
    assert bundle.session_id == "test-session-id"
    assert bundle.turn_id == "test-turn-id"
    assert bundle.request_summary is not None
    assert bundle.policy_snapshot is not None
    assert bundle.slot_snapshot is not None

    policy_data = json.loads(bundle.policy_snapshot)
    assert "reasoning_budget" in policy_data
    assert "turn_token_budget" in policy_data
    assert "tool_filter_active" in policy_data

    slot_data = json.loads(bundle.slot_snapshot)
    assert slot_data["slot_id"] == 42
    assert slot_data["temperature"] == "hot"
    assert slot_data["slot_saved_path"] == "/tmp/slot.bin"


@pytest.mark.asyncio
async def test_failure_bundle_shape_parity():
    """Both error paths produce FailureBundles with identical field coverage."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()
    mock_failure_store = MagicMock()
    mock_failure_store.record = AsyncMock()

    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.slot_id = None

    mock_turn = MagicMock()
    mock_turn.id = "test-turn-id"
    mock_turn.iterations = 0
    mock_turn.tool_calls_made = 0
    mock_turn.transitions = []
    mock_turn.reasoning_budget = None

    mock_session_store.insert_turn = AsyncMock(return_value=None)
    mock_session_store.update_turn = AsyncMock(return_value=None)
    mock_session_store.append_transition = AsyncMock(return_value=None)
    mock_session_store.append_message = AsyncMock(return_value=None)
    mock_session_store.get_messages = AsyncMock(return_value=[])

    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        failure_store=mock_failure_store,
    )

    # ContextTooLargeError
    mock_context_builder.build = AsyncMock(
        side_effect=ContextTooLargeError("too big")
    )
    mock_failure_store.record.reset_mock()

    with (
        patch.object(orchestrator, "_create_turn", return_value=mock_turn),
        patch.object(orchestrator, "_persist_turn", AsyncMock()),
        patch.object(orchestrator, "_transition", AsyncMock()),
    ):
        await orchestrator.process_turn(
            session=mock_session,
            user_message=Message(role="user", content="overflow"),
            respond_callback=AsyncMock(),
        )

    ctx_bundle = mock_failure_store.record.call_args[0][0]

    # Generic Exception
    mock_context_builder.build = AsyncMock(side_effect=RuntimeError("boom"))
    mock_failure_store.record.reset_mock()

    with (
        patch.object(orchestrator, "_create_turn", return_value=mock_turn),
        patch.object(orchestrator, "_persist_turn", AsyncMock()),
        patch.object(orchestrator, "_transition", AsyncMock()),
    ):
        await orchestrator.process_turn(
            session=mock_session,
            user_message=Message(role="user", content="boom"),
            respond_callback=AsyncMock(),
        )

    exc_bundle = mock_failure_store.record.call_args[0][0]

    # Same fields populated
    assert ctx_bundle.request_summary is not None
    assert exc_bundle.request_summary is not None
    assert ctx_bundle.policy_snapshot is not None
    assert exc_bundle.policy_snapshot is not None
    assert ctx_bundle.slot_snapshot is not None
    assert exc_bundle.slot_snapshot is not None
    assert ctx_bundle.tool_chain is not None
    assert exc_bundle.tool_chain is not None
