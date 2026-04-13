"""Tests for orchestrator error handling."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import Message
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
