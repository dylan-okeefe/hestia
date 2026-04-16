"""Tests for orchestrator error handling."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import ChatResponse, Message
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.types import TurnState


@pytest.mark.asyncio
async def test_tool_chain_unbound_error():
    """Test that tool_chain is properly initialized before error handler uses it.

    If ContextBuilder.build() fails early (before the main loop), the error handler
    should still be able to record the failure bundle with tool_chain="[]".
    This tests the fix for the UnboundLocalError where tool_chain was defined
    inside the inner try block but referenced in the except handler.
    """
    # Setup mocks
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()
    mock_failure_store = MagicMock()

    # Make context builder raise an error early (simulating line 166-172 in original)
    mock_context_builder.build = AsyncMock(side_effect=RuntimeError("build failed"))

    # Setup session store mocks
    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.slot_id = None

    mock_turn = MagicMock()
    mock_turn.id = "test-turn-id"
    mock_turn.iterations = 0
    mock_turn.tool_calls_made = 0
    mock_turn.transitions = []

    mock_session_store.insert_turn = AsyncMock(return_value=None)
    mock_session_store.update_turn = AsyncMock(return_value=None)
    mock_session_store.append_transition = AsyncMock(return_value=None)
    mock_session_store.append_message = AsyncMock(return_value=None)
    mock_session_store.get_messages = AsyncMock(return_value=[])

    # Create orchestrator
    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        confirm_callback=None,
        failure_store=mock_failure_store,
    )

    # Mock _create_turn to return our mock turn
    with patch.object(orchestrator, '_create_turn', return_value=mock_turn):
        # Mock _persist_turn
        with patch.object(orchestrator, '_persist_turn', AsyncMock()):
            # Mock _transition
            with patch.object(orchestrator, '_transition', AsyncMock()):
                # Test that the error handler doesn't crash with UnboundLocalError
                user_message = Message(role="user", content="test message")
                respond_callback = AsyncMock()

                # This should complete without raising UnboundLocalError
                await orchestrator.process_turn(
                    session=mock_session,
                    user_message=user_message,
                    respond_callback=respond_callback,
                )

                # Verify that respond_callback was called with the error
                respond_callback.assert_called_once()
                call_args = respond_callback.call_args[0][0]
                assert "Error:" in call_args
                assert "build failed" in call_args

                # Verify failure store was called with tool_chain="[]"
                mock_failure_store.record.assert_called_once()
                bundle = mock_failure_store.record.call_args[0][0]
                assert bundle.tool_chain == json.dumps([])


@pytest.mark.asyncio
async def test_failure_bundle_enriched_fields_populated():
    """Test that enriched failure bundle fields are populated on error.

    When both failure_store and trace_store are configured, the orchestrator
    should populate request_summary, policy_snapshot, slot_snapshot, and trace_id.
    """
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()
    mock_failure_store = MagicMock()
    mock_trace_store = MagicMock()

    # Trigger an error early via context builder
    mock_context_builder.build = AsyncMock(side_effect=RuntimeError("inference timeout"))

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
        confirm_callback=None,
        failure_store=mock_failure_store,
        trace_store=mock_trace_store,
    )

    with patch.object(orchestrator, '_create_turn', return_value=mock_turn):
        with patch.object(orchestrator, '_persist_turn', AsyncMock()):
            with patch.object(orchestrator, '_transition', AsyncMock()):
                long_content = "x" * 250
                user_message = Message(role="user", content=long_content)
                respond_callback = AsyncMock()

                await orchestrator.process_turn(
                    session=mock_session,
                    user_message=user_message,
                    respond_callback=respond_callback,
                )

                mock_failure_store.record.assert_called_once()
                bundle = mock_failure_store.record.call_args[0][0]

                # All four enriched fields should be non-None
                assert bundle.request_summary is not None
                assert bundle.request_summary.endswith("...")
                assert len(bundle.request_summary) == 203  # 200 chars + "..."

                assert bundle.policy_snapshot is not None
                policy_data = json.loads(bundle.policy_snapshot)
                assert "reasoning_budget" in policy_data
                assert "turn_token_budget" in policy_data
                assert "tool_filter_active" in policy_data

                assert bundle.slot_snapshot is not None
                slot_data = json.loads(bundle.slot_snapshot)
                assert slot_data["slot_id"] == 42
                assert slot_data["temperature"] == "hot"
                assert slot_data["slot_saved_path"] == "/tmp/slot.bin"

                assert bundle.trace_id is not None

                # Trace should be recorded with the same ID
                mock_trace_store.record.assert_called_once()
                trace = mock_trace_store.record.call_args[0][0]
                assert trace.id == bundle.trace_id


@pytest.mark.asyncio
async def test_post_done_respond_callback_error_no_illegal_transition() -> None:
    """Delivery failure after DONE must not raise IllegalTransitionError.

    When the model returns a successful stop response and respond_callback
    raises while sending the final message to the user, the orchestrator
    should keep the turn in DONE and log the delivery error instead of
    attempting an illegal transition to FAILED.
    """
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    # Simulate successful model response
    mock_inference.chat = AsyncMock(
        return_value=ChatResponse(
            content="Hello, world!",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    mock_context_builder.build = AsyncMock(
        return_value=MagicMock(messages=[])
    )

    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.filter_tools.return_value = None
    mock_policy.turn_token_budget.return_value = 4000

    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.list_names.return_value = []

    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session.slot_id = None

    mock_turn = MagicMock()
    mock_turn.id = "test-turn-id"
    mock_turn.iterations = 0
    mock_turn.tool_calls_made = 0
    mock_turn.transitions = []
    mock_turn.state = TurnState.RECEIVED

    mock_session_store.insert_turn = AsyncMock(return_value=None)
    mock_session_store.update_turn = AsyncMock(return_value=None)
    mock_session_store.append_transition = AsyncMock(return_value=None)
    mock_session_store.append_message = AsyncMock(return_value=None)
    mock_session_store.get_messages = AsyncMock(return_value=[])

    orchestrator = Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        confirm_callback=None,
    )

    with (
        patch.object(orchestrator, '_create_turn', return_value=mock_turn),
        patch.object(orchestrator, '_persist_turn', AsyncMock()),
    ):
        user_message = Message(role="user", content="hi")

        # First call (successful delivery) raises; fallback call succeeds
        respond_callback = AsyncMock(
            side_effect=[RuntimeError("send failed"), None]
        )

        turn = await orchestrator.process_turn(
            session=mock_session,
            user_message=user_message,
            respond_callback=respond_callback,
        )

        # Turn should remain DONE (no IllegalTransitionError raised)
        assert turn.state == TurnState.DONE
        # respond_callback called twice: first for content (failed),
        # second for fallback error notification (succeeded)
        assert respond_callback.call_count == 2
        assert "Hello, world!" in respond_callback.call_args_list[0][0][0]
        assert "Error delivering response" in respond_callback.call_args_list[1][0][0]
