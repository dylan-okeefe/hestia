"""Tests for TurnAssembly skill index wiring."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message
from hestia.orchestrator.assembly import TurnAssembly
from hestia.orchestrator.types import TurnContext, TurnState


@pytest.mark.asyncio
async def test_skill_index_wired_when_builder_present():
    """When skill_index_builder is provided, its output is set on the context builder."""
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(return_value=MagicMock())

    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = []

    mock_policy = MagicMock()
    mock_policy.filter_tools.return_value = None

    mock_store = MagicMock()
    mock_store.get_messages = AsyncMock(return_value=[])
    mock_store.append_message = AsyncMock()

    mock_skill_index = MagicMock()
    mock_skill_index.text = "test skill index"

    mock_skill_index_builder = MagicMock()
    mock_skill_index_builder.build_index = AsyncMock(return_value=mock_skill_index)

    assembly = TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=mock_policy,
        session_store=mock_store,
        skill_index_builder=mock_skill_index_builder,
    )

    mock_turn = MagicMock()
    mock_turn.state = TurnState.RECEIVED

    mock_session = MagicMock()
    mock_session.id = "test-session"
    mock_session.platform = "test"
    mock_session.platform_user = "user"
    mock_session.slot_id = None

    user_message = Message(role="user", content="hello")

    ctx = TurnContext(
        turn=mock_turn,
        user_message=user_message,
        system_prompt="test",
        respond_callback=AsyncMock(),
        session=mock_session,
    )

    async def fake_transition(turn, state, note):
        turn.state = state

    await assembly.prepare(mock_session, ctx, fake_transition)

    mock_skill_index_builder.build_index.assert_awaited_once()
    mock_builder.set_skill_index_prefix.assert_called_once_with("test skill index")


@pytest.mark.asyncio
async def test_skill_index_not_wired_when_builder_absent():
    """When skill_index_builder is None, set_skill_index_prefix is not called."""
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(return_value=MagicMock())

    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = []

    mock_policy = MagicMock()
    mock_policy.filter_tools.return_value = None

    mock_store = MagicMock()
    mock_store.get_messages = AsyncMock(return_value=[])
    mock_store.append_message = AsyncMock()

    assembly = TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=mock_policy,
        session_store=mock_store,
        skill_index_builder=None,
    )

    mock_turn = MagicMock()
    mock_turn.state = TurnState.RECEIVED

    mock_session = MagicMock()
    mock_session.id = "test-session"
    mock_session.platform = "test"
    mock_session.platform_user = "user"
    mock_session.slot_id = None

    user_message = Message(role="user", content="hello")

    ctx = TurnContext(
        turn=mock_turn,
        user_message=user_message,
        system_prompt="test",
        respond_callback=AsyncMock(),
        session=mock_session,
    )

    async def fake_transition(turn, state, note):
        turn.state = state

    await assembly.prepare(mock_session, ctx, fake_transition)

    mock_builder.set_skill_index_prefix.assert_not_called()
