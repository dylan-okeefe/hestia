"""Tests for per-session turn serialization."""

from __future__ import annotations

import asyncio
import contextlib
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
    manager.unref("sess-prune")
    manager.release_unused("sess-prune")
    assert "sess-prune" not in manager._locks


@pytest.mark.asyncio
async def test_release_unused_does_not_orphan_pending_waiter() -> None:
    """BUG-001: pruning during the release→waiter-resume window is forbidden.

    asyncio.Lock reports *unlocked* between release() and the waiter's
    resumption. Pruning in that window used to strand the waiter on an
    orphaned object while later arrivals got a fresh lock — two concurrent
    turns on one session. The manager must keep the entry (and hand later
    arrivals the same object) until the waiter has finished.
    """
    manager = SessionLockManager()
    first = await manager.acquire("sess-race")
    await first.acquire()  # the holder's critical section begins

    contender_running = asyncio.Event()
    contender_done = asyncio.Event()

    async def contender() -> None:
        second = await manager.acquire("sess-race")  # parks immediately
        # The contender must have received the SAME object, not a fresh one.
        assert second is first
        async with second:
            contender_running.set()
            await asyncio.sleep(0)
        contender_done.set()
        manager.unref("sess-race")

    task = asyncio.create_task(contender())
    await asyncio.sleep(0)  # let the contender park on the lock

    # Holder releases; manager then attempts to prune synchronously —
    # exactly the interleaving that used to orphan the waiter.
    first.release()
    manager.unref("sess-race")
    manager.release_unused("sess-race")

    assert "sess-race" in manager._locks, "lock entry was pruned with a waiter pending"
    assert not contender_done.is_set()

    await task
    assert contender_done.is_set()

    # Now genuinely idle: pruning succeeds.
    manager.release_unused("sess-race")
    assert "sess-race" not in manager._locks


@pytest.mark.asyncio
async def test_release_unused_respects_outstanding_refs() -> None:
    """A session with an outstanding acquire() reference is never pruned."""
    manager = SessionLockManager()
    _lock_a = await manager.acquire("sess-refs")  # turn A interest ref
    _lock_b = await manager.acquire("sess-refs")  # queued turn B interest ref
    manager.unref("sess-refs")  # A finished its critical section
    manager.release_unused("sess-refs")
    # B still holds a reference even though the lock is momentarily unlocked.
    assert "sess-refs" in manager._locks


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


@pytest.mark.asyncio
async def test_cancelled_turn_does_not_leak_lock_reference() -> None:
    """Review defect 2: a cancelled turn must still drop its interest
    reference (CancelledError bypasses except-Exception handlers), or the
    session's lock becomes permanently unprunable."""
    manager = SessionLockManager()

    started = asyncio.Event()

    async def turn() -> None:
        # Mirrors engine.process_turn: acquire -> async with -> finally unref.
        lock = await manager.acquire("sess-cancel")
        try:
            async with lock:
                started.set()
                await asyncio.Event().wait()  # hangs until cancelled
        finally:
            manager.unref("sess-cancel")

    task = asyncio.create_task(turn())
    await started.wait()

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # The cancelled turn released both the lock and its interest reference,
    # so the entry is prunable.
    manager.release_unused("sess-cancel")
    assert "sess-cancel" not in manager._locks
    assert "sess-cancel" not in manager._refs
