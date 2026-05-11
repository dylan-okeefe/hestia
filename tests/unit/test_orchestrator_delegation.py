"""Tests verifying Orchestrator delegates to phase classes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import ChatResponse, Message
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.types import TurnState


@pytest.mark.asyncio
async def test_orchestrator_delegates_to_turn_execution():
    """process_turn should delegate inference loop to TurnExecution.run()."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    mock_context_builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.list_names.return_value = []

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
    )

    with patch.object(
        orchestrator._execution, "run", new_callable=AsyncMock, return_value="Hello!"
    ) as mock_run:
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.slot_id = None

        mock_turn = MagicMock()
        mock_turn.id = "test-turn-id"
        mock_turn.iterations = 0
        mock_turn.tool_calls_made = 0
        mock_turn.transitions = []
        mock_turn.state = TurnState.RECEIVED

        with patch.object(orchestrator, "_create_turn", return_value=mock_turn), patch.object(
            orchestrator, "_persist_turn", AsyncMock()
        ):
            await orchestrator.process_turn(
                session=mock_session,
                user_message=Message(role="user", content="hi"),
                respond_callback=AsyncMock(),
            )

        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_delegates_to_turn_finalization():
    """process_turn should delegate finalization to TurnFinalization.finalize_turn()."""
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    mock_context_builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.list_names.return_value = []

    mock_inference.chat = AsyncMock(
        return_value=ChatResponse(
            content="Hello!",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
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
    )

    with patch.object(
        orchestrator._finalization, "finalize_turn", new_callable=AsyncMock
    ) as mock_finalize:
        mock_session = MagicMock()
        mock_session.id = "test-session-id"
        mock_session.slot_id = None

        mock_turn = MagicMock()
        mock_turn.id = "test-turn-id"
        mock_turn.iterations = 0
        mock_turn.tool_calls_made = 0
        mock_turn.transitions = []
        mock_turn.state = TurnState.RECEIVED

        with patch.object(orchestrator, "_create_turn", return_value=mock_turn), patch.object(
            orchestrator, "_persist_turn", AsyncMock()
        ):
            await orchestrator.process_turn(
                session=mock_session,
                user_message=Message(role="user", content="hi"),
                respond_callback=AsyncMock(),
            )

        mock_finalize.assert_awaited_once()
