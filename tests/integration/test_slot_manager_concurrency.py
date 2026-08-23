"""Concurrency stress tests for SlotManager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Session, SessionTemperature
from hestia.inference.slot_manager import SlotAssignment, SlotManager
from hestia.persistence.sessions import SessionStore


@pytest.fixture
def mock_inference():
    inf = AsyncMock()
    inf.slot_save = AsyncMock()
    inf.slot_erase = AsyncMock()
    inf.slot_restore = AsyncMock()
    return inf


@pytest.fixture
def mock_store():
    store = MagicMock(spec=SessionStore)
    store.get_session = AsyncMock(return_value=None)
    store.get_sessions_batch = AsyncMock(return_value=[])
    store.assign_slot = AsyncMock()
    store.release_slot = AsyncMock()
    store.update_saved_path = AsyncMock()
    return store


def _session(
    session_id: str,
    slot_id: int | None = None,
    slot_saved_path: str | None = None,
    temperature: SessionTemperature = SessionTemperature.HOT,
    last_active_at: datetime | None = None,
) -> Session:
    return Session(
        id=session_id,
        platform="test",
        platform_user="user",
        started_at=datetime.now(UTC),
        last_active_at=last_active_at or datetime.now(UTC),
        slot_id=slot_id,
        slot_saved_path=slot_saved_path,
        state="ACTIVE",
        temperature=temperature,
    )


async def test_eviction_with_slow_io_completes(mock_inference, mock_store, tmp_path) -> None:
    """An eviction whose slot_save/slot_erase I/O is slow still completes.

    BUG-002 fix: the pool lock is now held across eviction I/O, so concurrent
    acquire() calls serialize behind it instead of racing the freed slot.
    This test exercises the slow-I/O path end-to-end.
    """
    slot_dir = tmp_path / "slots"
    manager = SlotManager(
        inference=mock_inference,
        session_store=mock_store,
        slot_dir=slot_dir,
        pool_size=2,
    )

    # Pre-fill both slots
    manager._assignments[0] = "session-a"
    manager._assignments[1] = "session-b"

    # Make erase artificially slow
    erase_started = asyncio.Event()
    erase_continue = asyncio.Event()

    async def slow_erase(slot_id):
        erase_started.set()
        await erase_continue.wait()

    mock_inference.slot_erase.side_effect = slow_erase
    mock_inference.slot_save = AsyncMock()

    session_a = _session("session-a", slot_id=0, slot_saved_path="x.bin")
    session_b = _session("session-b", slot_id=1, slot_saved_path="x.bin")

    mock_store.get_sessions_batch = AsyncMock(
        return_value={session_a.id: session_a, session_b.id: session_b}
    )
    mock_store.get_session = AsyncMock(side_effect=lambda sid: session_a if sid == "session-a" else session_b)

    # Start an acquire that will need to evict
    acquire_task = asyncio.create_task(
        manager.acquire(_session("session-c", temperature=SessionTemperature.COLD))
    )

    # Wait until erase has started (inside the held pool lock)
    await asyncio.wait_for(erase_started.wait(), timeout=1.0)

    # While erase is blocked, the acquire task shouldn't be done yet
    assert not acquire_task.done()

    # Let erase finish
    erase_continue.set()
    result = await asyncio.wait_for(acquire_task, timeout=1.0)
    assert isinstance(result, SlotAssignment)
    assert result.slot_id == 0  # session-c took over evicted session-a's slot


async def test_slot_save_400_leaves_session_cold(mock_inference, mock_store, tmp_path):
    """If slot_save fails, the session should not be marked WARM."""
    from hestia.errors import InferenceServerError

    slot_dir = tmp_path / "slots"
    manager = SlotManager(
        inference=mock_inference,
        session_store=mock_store,
        slot_dir=slot_dir,
        pool_size=2,
    )

    mock_inference.slot_save.side_effect = InferenceServerError("400 Bad Request")

    session = _session("session-a", slot_id=0)
    manager._assignments[0] = "session-a"  # save() requires registered ownership

    with pytest.raises(InferenceServerError):
        await manager.save(session)

    mock_store.update_saved_path.assert_not_called()


async def test_save_skips_when_slot_reassigned(mock_inference, mock_store, tmp_path):
    """BUG-002: saving into a slot now owned by another session must not
    snapshot the other owner's KV cache under our filename."""
    slot_dir = tmp_path / "slots"
    manager = SlotManager(
        inference=mock_inference,
        session_store=mock_store,
        slot_dir=slot_dir,
        pool_size=2,
    )
    manager._assignments[0] = "session-b"  # slot reassigned to someone else

    stale = _session("session-a", slot_id=0)
    await manager.save(stale)

    mock_inference.slot_save.assert_not_called()
    mock_store.update_saved_path.assert_not_called()


async def test_erase_skips_server_call_when_slot_reassigned(mock_inference, mock_store, tmp_path):
    """BUG-002: erasing a slot now owned by another session must not wipe the
    new owner's live KV cache; we only release our own DB record."""
    slot_dir = tmp_path / "slots"
    manager = SlotManager(
        inference=mock_inference,
        session_store=mock_store,
        slot_dir=slot_dir,
        pool_size=2,
    )
    manager._assignments[0] = "session-b"

    stale = _session("session-a", slot_id=0)
    await manager.erase(stale)

    mock_inference.slot_erase.assert_not_called()
    mock_store.release_slot.assert_awaited_once()
