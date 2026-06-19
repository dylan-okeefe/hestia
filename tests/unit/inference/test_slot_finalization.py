"""Unit tests for slot lifecycle on turn finalization (L221 §3)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.orchestrator.finalization import TurnFinalization
from hestia.orchestrator.types import Turn, TurnContext, TurnState


def _make_session(slot_id: int | None = 7) -> Session:
    return Session(
        id="test-session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        slot_id=slot_id,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


def _make_turn(state: TurnState = TurnState.DONE) -> Turn:
    return Turn(
        id="turn-1",
        session_id="test-session",
        state=state,
        user_message=Message(role="user", content="hello"),
        started_at=datetime.now(UTC),
    )


def _make_ctx(state: TurnState = TurnState.DONE, slot_id: int | None = 7) -> TurnContext:
    return TurnContext(
        turn=_make_turn(state),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(slot_id),
    )


@pytest.mark.asyncio
async def test_failed_turn_erases_live_slot():
    """A failed turn erases the live slot without saving KV cache."""
    slot_manager = MagicMock()
    slot_manager.save = AsyncMock()
    slot_manager.erase = AsyncMock()

    finalization = TurnFinalization(slot_manager=slot_manager)

    await finalization.finalize_turn(
        ctx=_make_ctx(state=TurnState.FAILED, slot_id=7),
        turn_start_time=datetime.now(UTC),
        trace_record_id=None,
    )

    slot_manager.erase.assert_awaited_once()
    assert slot_manager.erase.await_args[0][0].slot_id == 7
    slot_manager.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_done_turn_saves_slot():
    """A DONE turn saves the slot as before."""
    slot_manager = MagicMock()
    slot_manager.save = AsyncMock()
    slot_manager.erase = AsyncMock()

    finalization = TurnFinalization(slot_manager=slot_manager)

    await finalization.finalize_turn(
        ctx=_make_ctx(state=TurnState.DONE, slot_id=7),
        turn_start_time=datetime.now(UTC),
        trace_record_id=None,
    )

    slot_manager.save.assert_awaited_once()
    assert slot_manager.save.await_args[0][0].slot_id == 7
    slot_manager.erase.assert_not_awaited()
