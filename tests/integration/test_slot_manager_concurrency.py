"""Concurrency stress tests for SlotManager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
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
        started_at=datetime.now(timezone.utc),
        last_active_at=last_active_at or datetime.now(timezone.utc),
        slot_id=slot_id,
        slot_saved_path=slot_saved_path,
        state="ACTIVE",
        temperature=temperature,
    )


async def test_concurrent_acquire_no_stall_on_slow_erase(mock_inference, mock_store, tmp_path):
    """Concurrent acquire() calls should not block on a slow slot_erase."""
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

    mock_store.get_sessions_batch = AsyncMock(return_value=[session_a, session_b])
    mock_store.get_session = AsyncMock(side_effect=lambda sid: session_a if sid == "session-a" else session_b)

    # Start an acquire that will need to evict
    acquire_task = asyncio.create_task(
        manager.acquire(_session("session-c", temperature=SessionTemperature.COLD))
    )

    # Wait until erase has started (lock released)
    await asyncio.wait_for(erase_started.wait(), timeout=1.0)

    # While erase is blocked, the acquire task shouldn't be done yet
    assert not acquire_task.done()

    # Let erase finish
    erase_continue.set()
    result = await asyncio.wait_for(acquire_task, timeout=1.0)
    assert isinstance(result, SlotAssignment)


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

    with pytest.raises(InferenceServerError):
        await manager.save(session)

    mock_store.update_saved_path.assert_not_called()
