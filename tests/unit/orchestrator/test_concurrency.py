"""Tests for per-session turn serialization."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.lock import SessionLockManager
from hestia.orchestrator.types import TurnState


def _make_session(session_id: str = "sess-1") -> Session:
    return Session(
        id=session_id,
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


def _make_orchestrator() -> Orchestrator:
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = MagicMock()
    mock_policy = MagicMock()

    mock_context_builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    mock_tool_registry.meta_tool_schemas.return_value = []
    mock_tool_registry.list_names.return_value = []
    mock_policy.filter_tools.return_value = []
    mock_policy.reasoning_budget.return_value = 2048
    mock_policy.turn_token_budget.return_value = 4000

    mock_message_store = MagicMock()
    mock_message_store.get_messages = AsyncMock(return_value=[])
    mock_message_store.append_message = AsyncMock()
    mock_turn_store = MagicMock()
    mock_turn_store.insert_turn = AsyncMock()
    mock_turn_store.update_turn = AsyncMock()
    mock_turn_store.append_transition = AsyncMock()

    return Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        message_store=mock_message_store,
        turn_store=mock_turn_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
    )


@pytest.mark.asyncio
async def test_same_session_turns_are_sequential() -> None:
    """Concurrent process_turn calls for the same session execute one after another."""
    orchestrator = _make_orchestrator()
    order: list[int] = []

    async def slow_run(_ctx, _transition, _set_typing):
        order.append(1)
        await asyncio.sleep(0.05)
        order.append(2)
        _ctx.turn.state = TurnState.DONE
        return "done"

    with patch.object(orchestrator._execution, "run", side_effect=slow_run):
        session = _make_session("sess-same")
        user_msg = Message(role="user", content="hi")

        async def turn():
            return await orchestrator.process_turn(
                session=session,
                user_message=user_msg,
                respond_callback=AsyncMock(),
            )

        t1 = asyncio.create_task(turn())
        t2 = asyncio.create_task(turn())
        await asyncio.gather(t1, t2)

    # Each turn's critical section should not interleave.
    assert order == [1, 2, 1, 2]


@pytest.mark.asyncio
async def test_different_session_turns_run_in_parallel() -> None:
    """Concurrent process_turn calls for different sessions may overlap."""
    orchestrator = _make_orchestrator()
    order: list[str] = []

    async def slow_run(_ctx, _transition, _set_typing):
        order.append(f"start-{_ctx.turn.session_id}")
        await asyncio.sleep(0.05)
        order.append(f"end-{_ctx.turn.session_id}")
        _ctx.turn.state = TurnState.DONE
        return "done"

    with patch.object(orchestrator._execution, "run", side_effect=slow_run):
        session_a = _make_session("sess-a")
        session_b = _make_session("sess-b")
        user_msg = Message(role="user", content="hi")

        async def turn(sess: Session):
            return await orchestrator.process_turn(
                session=sess,
                user_message=user_msg,
                respond_callback=AsyncMock(),
            )

        t1 = asyncio.create_task(turn(session_a))
        t2 = asyncio.create_task(turn(session_b))
        await asyncio.gather(t1, t2)

    # Both turns started before either finished.
    assert order[0].startswith("start-")
    assert order[1].startswith("start-")


@pytest.mark.asyncio
async def test_lock_released_after_exception() -> None:
    """The session lock is released even if the turn raises unexpectedly."""
    orchestrator = _make_orchestrator()
    lock_manager = orchestrator._lock_manager
    lock = await lock_manager.acquire("sess-exc")

    with patch.object(
        orchestrator._execution, "run", side_effect=RuntimeError("boom")
    ):
        session = _make_session("sess-exc")
        user_msg = Message(role="user", content="hi")
        turn = await orchestrator.process_turn(
            session=session,
            user_message=user_msg,
            respond_callback=AsyncMock(),
        )

    assert turn.state == TurnState.FAILED
    assert not lock.locked()


@pytest.mark.asyncio
async def test_lock_manager_release_unused() -> None:
    """release_unused prunes locks that are no longer held."""
    manager = SessionLockManager()
    lock = await manager.acquire("sess-prune")
    async with lock:
        pass
    manager.release_unused("sess-prune")
    assert "sess-prune" not in manager._locks


@pytest.mark.asyncio
async def test_reentrant_process_turn_raises() -> None:
    """Calling process_turn re-entrantly on the same session raises instead of deadlocking."""
    orchestrator = _make_orchestrator()
    session = _make_session("sess-reentrant")
    user_msg = Message(role="user", content="hi")

    async def reentrant_run(ctx, transition, set_typing):
        # Simulate a callback that tries to start another turn on the same session.
        with pytest.raises(RuntimeError, match="Re-entrant process_turn"):
            await orchestrator.process_turn(
                session=session,
                user_message=user_msg,
                respond_callback=AsyncMock(),
            )
        ctx.turn.state = TurnState.DONE
        return "done"

    with patch.object(orchestrator._execution, "run", side_effect=reentrant_run):
        turn = await orchestrator.process_turn(
            session=session,
            user_message=user_msg,
            respond_callback=AsyncMock(),
        )

    assert turn.state == TurnState.DONE


@pytest.mark.asyncio
async def test_subagent_turn_on_different_session_does_not_raise() -> None:
    """A nested turn on a different session is allowed (subagents use distinct sessions)."""
    orchestrator = _make_orchestrator()
    session_a = _make_session("sess-a")
    session_b = _make_session("sess-b")
    user_msg = Message(role="user", content="hi")

    async def nested_run(ctx, transition, set_typing):
        # A subagent turn on a different session should succeed.
        await orchestrator.process_turn(
            session=session_b,
            user_message=user_msg,
            respond_callback=AsyncMock(),
        )
        ctx.turn.state = TurnState.DONE
        return "done"

    with patch.object(orchestrator._execution, "run", side_effect=nested_run):
        turn_a = await orchestrator.process_turn(
            session=session_a,
            user_message=user_msg,
            respond_callback=AsyncMock(),
        )

    assert turn_a.state == TurnState.DONE
