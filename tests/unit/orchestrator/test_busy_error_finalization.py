"""L232 §5: InferenceBusyError produces a friendly user message, not "Error: ..."."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.errors import InferenceBusyError
from hestia.orchestrator.finalization import TurnFinalization, sanitize_user_error
from hestia.orchestrator.types import Turn, TurnContext, TurnState


def _make_ctx() -> TurnContext:
    session = Session(
        id="test-session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    turn = Turn(
        id="turn-1",
        session_id="test-session",
        state=TurnState.RECEIVED,
        user_message=Message(role="user", content="hello"),
        started_at=datetime.now(UTC),
    )
    return TurnContext(
        turn=turn,
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=session,
    )


BUSY_MESSAGE = "I'm busy working on another request right now — please try again in a moment."


def test_sanitize_busy_error_returns_friendly_message():
    assert sanitize_user_error(InferenceBusyError("at capacity")) == BUSY_MESSAGE


@pytest.mark.asyncio
async def test_handle_unexpected_error_sends_busy_message_verbatim():
    """The engine catch-all path sends the friendly message, not 'Error: ...'."""
    finalization = TurnFinalization()
    ctx = _make_ctx()
    transition = AsyncMock()

    await finalization.handle_unexpected_error(
        ctx,
        InferenceBusyError("at capacity"),
        trace_record_id=None,
        transition=transition,
    )

    ctx.respond_callback.assert_awaited_once_with(BUSY_MESSAGE)
    sent = ctx.respond_callback.await_args[0][0]
    assert not sent.startswith("Error:")
    transition.assert_awaited_once_with(ctx.turn, TurnState.FAILED, "")
    assert ctx.turn.error == "at capacity"
