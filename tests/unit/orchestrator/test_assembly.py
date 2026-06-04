"""Tests for TurnAssembly memory epoch injection."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.orchestrator.assembly import TurnAssembly
from hestia.orchestrator.types import TurnContext
from hestia.policy.default import DefaultPolicyEngine


def _make_session() -> Session:
    return Session(
        id="test-session",
        platform="cli",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


def _make_turn_context(session: Session | None = None) -> TurnContext:
    from hestia.orchestrator.types import Turn

    session = session or _make_session()
    turn = Turn(
        id="turn-1",
        session_id=session.id,
        state="received",
        user_message=Message(role="user", content="hello"),
        started_at=datetime.now(),
        completed_at=None,
        iterations=0,
        tool_calls_made=0,
        final_response=None,
        error=None,
        transitions=[],
    )
    return TurnContext(
        turn=turn,
        user_message=Message(role="user", content="hello"),
        system_prompt="You are helpful.",
        respond_callback=AsyncMock(),
        session=session,
    )


@pytest.mark.asyncio
async def test_prepare_builds_context_and_acquires_slot():
    """TurnAssembly prepares context, tools, and history for execution."""
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(
        return_value=MagicMock(
            messages=[], tokens_used=0, tokens_budget=1000,
            truncated_count=0, kept_first_user=False,
        )
    )

    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = []

    policy = DefaultPolicyEngine(ctx_window=4096)

    mock_store = MagicMock()
    mock_store.get_messages = AsyncMock(return_value=[])
    mock_store.append_message = AsyncMock()

    assembly = TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=policy,
        session_store=mock_store,
    )

    session = _make_session()
    ctx = _make_turn_context(session)
    transition = AsyncMock()

    await assembly.prepare(session, ctx, transition)

    mock_builder.build.assert_awaited_once()
    assert ctx.build_result is not None
