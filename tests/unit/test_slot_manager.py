"""Unit tests for SlotManager."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from hestia.core.types import ChatResponse, Session, SessionState, SessionTemperature
from hestia.inference import SlotManager
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore


class FakeInferenceClient:
    """Fake inference client that records slot operations."""

    def __init__(self):
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._saved_paths: dict[int, str] = {}  # slot_id -> path

    async def slot_save(self, slot_id: int, filename: str) -> None:
        self.calls.append(("slot_save", (slot_id, filename)))
        self._saved_paths[slot_id] = filename

    async def slot_restore(self, slot_id: int, filename: str) -> None:
        self.calls.append(("slot_restore", (slot_id, filename)))
        self._saved_paths[slot_id] = filename

    async def slot_erase(self, slot_id: int) -> None:
        self.calls.append(("slot_erase", (slot_id,)))
        self._saved_paths.pop(slot_id, None)

    async def chat(
        self, messages: list, tools: list | None = None, slot_id: int | None = None, **kwargs
    ) -> ChatResponse:
        return ChatResponse(
            content="Test",
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    store = SessionStore(db)
    yield store
    await db.close()


@pytest.fixture
def slot_dir(tmp_path):
    """Create a temp slot directory."""
    return tmp_path / "slots"


@pytest.mark.asyncio
async def test_acquire_cold_session(store, slot_dir):
    """COLD session gets fresh slot, no restore."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    assert session.temperature == SessionTemperature.COLD

    assignment = await manager.acquire(session)

    assert assignment.slot_id == 0
    assert assignment.restored_from_disk is False
    assert "slot_restore" not in [c[0] for c in inference.calls]

    # Session is now HOT
    fetched = await store.get_session(session.id)
    assert fetched.temperature == SessionTemperature.HOT
    assert fetched.slot_id == 0


@pytest.mark.asyncio
async def test_acquire_warm_session_restores_from_disk(store, slot_dir):
    """WARM session with saved_path gets restored from disk."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    # Create session, assign slot, then release to WARM
    session = await store.get_or_create_session("cli", "user1")
    await store.assign_slot(session.id, slot_id=0)
    await store.release_slot(
        session.id,
        demote_to=SessionTemperature.WARM,
        saved_path="/slots/test_session.bin",
    )

    # Reload to get updated state
    session = await store.get_session(session.id)
    assert session.temperature == SessionTemperature.WARM
    assert session.slot_saved_path == "/slots/test_session.bin"

    assignment = await manager.acquire(session)

    assert assignment.slot_id == 0
    assert assignment.restored_from_disk is True
    assert inference.calls == [("slot_restore", (0, "/slots/test_session.bin"))]

    # Session is now HOT, saved_path cleared
    fetched = await store.get_session(session.id)
    assert fetched.temperature == SessionTemperature.HOT
    assert fetched.slot_id == 0
    assert fetched.slot_saved_path is None


@pytest.mark.asyncio
async def test_acquire_hot_session_no_op(store, slot_dir):
    """HOT session with matching assignment returns existing slot."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    # Create and acquire session
    session = await store.get_or_create_session("cli", "user1")
    assignment1 = await manager.acquire(session)
    assert assignment1.slot_id == 0

    # Clear recorded calls
    inference.calls.clear()

    # Re-acquire same session (still HOT)
    session = await store.get_session(session.id)
    assignment2 = await manager.acquire(session)

    assert assignment2.slot_id == 0
    assert assignment2.restored_from_disk is False
    # No inference calls on re-acquire of HOT session
    assert inference.calls == []


@pytest.mark.asyncio
async def test_save_checkpoints_without_demoting(store, slot_dir):
    """save() checkpoints to disk but keeps session HOT."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    await manager.acquire(session)

    # Refresh session to get updated slot_id
    session = await store.get_session(session.id)

    # Clear calls from acquire
    inference.calls.clear()

    await manager.save(session)

    # Should have called slot_save
    assert len(inference.calls) == 1
    assert inference.calls[0][0] == "slot_save"
    # Session still HOT
    fetched = await store.get_session(session.id)
    assert fetched.temperature == SessionTemperature.HOT
    assert fetched.slot_id == 0
    # But saved_path is set
    assert fetched.slot_saved_path is not None


@pytest.mark.asyncio
async def test_full_pool_evicts_lru(store, slot_dir):
    """When pool is full, LRU session is evicted."""
    import asyncio

    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=2,  # Small pool for testing
    )

    # Create and acquire session A
    session_a = await store.get_or_create_session("cli", "user1")
    assignment_a = await manager.acquire(session_a)
    assert assignment_a.slot_id == 0

    # Wait a moment to ensure different timestamps
    await asyncio.sleep(0.01)

    # Create and acquire session B
    session_b = await store.get_or_create_session("cli", "user2")
    assignment_b = await manager.acquire(session_b)
    assert assignment_b.slot_id == 1

    # Clear calls
    inference.calls.clear()

    # Create and acquire session C (should evict A, the LRU)
    session_c = await store.get_or_create_session("cli", "user3")
    assignment_c = await manager.acquire(session_c)

    # C should get slot 0 (evicted from A)
    assert assignment_c.slot_id == 0

    # A should be WARM with saved_path
    fetched_a = await store.get_session(session_a.id)
    assert fetched_a.temperature == SessionTemperature.WARM
    assert fetched_a.slot_saved_path is not None

    # B should still be HOT
    fetched_b = await store.get_session(session_b.id)
    assert fetched_b.temperature == SessionTemperature.HOT
    assert fetched_b.slot_id == 1

    # Should have saved and erased A's slot
    call_names = [c[0] for c in inference.calls]
    assert "slot_save" in call_names
    assert "slot_erase" in call_names


@pytest.mark.asyncio
async def test_evict_then_reacquire_restores(store, slot_dir):
    """Evicted session can be re-acquired and restored from disk."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=1,  # Force immediate eviction
    )

    # Acquire session A
    session_a = await store.get_or_create_session("cli", "user1")
    assignment_a = await manager.acquire(session_a)
    assert assignment_a.slot_id == 0

    # Refresh and save A's state
    session_a = await store.get_session(session_a.id)
    await manager.save(session_a)
    saved_path = (await store.get_session(session_a.id)).slot_saved_path

    # Clear calls
    inference.calls.clear()

    # Acquire session B (evicts A)
    session_b = await store.get_or_create_session("cli", "user2")
    assignment_b = await manager.acquire(session_b)
    assert assignment_b.slot_id == 0  # Same slot, evicted A

    # Clear calls
    inference.calls.clear()

    # Re-acquire session A (evicts B, restores A)
    session_a = await store.get_session(session_a.id)
    assignment_a2 = await manager.acquire(session_a)

    assert assignment_a2.restored_from_disk is True
    # Should have saved B, erased B's slot, restored A
    call_names = [c[0] for c in inference.calls]
    assert "slot_save" in call_names
    assert "slot_erase" in call_names
    assert "slot_restore" in call_names


@pytest.mark.asyncio
async def test_acquire_hot_session_stale_assignment_map(store, slot_dir):
    """Session marked HOT but assignment map empty (restart) reallocates."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    # Create session marked HOT with slot_id but no saved_path
    session = await store.get_or_create_session("cli", "user1")
    await store.assign_slot(session.id, slot_id=2)

    # Reload to get HOT state
    session = await store.get_session(session.id)
    assert session.temperature == SessionTemperature.HOT
    assert session.slot_id == 2

    # But assignment map is empty (simulating restart)
    # Acquire should detect mismatch and reallocate
    assignment = await manager.acquire(session)

    # Should get a slot (could be 0, not necessarily 2)
    assert assignment.slot_id in range(4)
    # Should NOT have restored (no saved_path)
    assert assignment.restored_from_disk is False


@pytest.mark.asyncio
async def test_save_failure_propagates(store, slot_dir):
    """save() propagates exceptions from inference (orchestrator catches them)."""

    class FailingInference(FakeInferenceClient):
        async def slot_save(self, slot_id: int, filename: str) -> None:
            raise RuntimeError("Disk full")

    inference = FailingInference()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    await manager.acquire(session)

    # Refresh session to get slot_id
    session = await store.get_session(session.id)

    # Save should raise (orchestrator is responsible for catching)
    with pytest.raises(RuntimeError, match="Disk full"):
        await manager.save(session)


@pytest.mark.asyncio
async def test_evict_by_id(store, slot_dir):
    """evict_by_id forcibly evicts a specific session."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    await manager.acquire(session)

    # Clear calls from acquire
    inference.calls.clear()

    await manager.evict_by_id(session.id)

    # Session should be WARM
    fetched = await store.get_session(session.id)
    assert fetched.temperature == SessionTemperature.WARM
    assert fetched.slot_id is None
    assert fetched.slot_saved_path is not None

    # Should have saved and erased
    call_names = [c[0] for c in inference.calls]
    assert "slot_save" in call_names
    assert "slot_erase" in call_names


@pytest.mark.asyncio
async def test_acquire_warm_rolls_back_assignment_on_restore_failure(store, slot_dir):
    """If slot_restore raises during WARM acquire, the assignment map rolls back."""

    class FailingRestoreInference(FakeInferenceClient):
        async def slot_restore(self, slot_id: int, filename: str) -> None:
            raise RuntimeError("Corrupt save file")

    inference = FailingRestoreInference()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    # Set up a WARM session
    session = await store.get_or_create_session("cli", "user1")
    await store.assign_slot(session.id, slot_id=0)
    await store.release_slot(
        session.id,
        demote_to=SessionTemperature.WARM,
        saved_path="/slots/test.bin",
    )
    session = await store.get_session(session.id)

    # acquire should raise and leave _assignments empty
    with pytest.raises(RuntimeError, match="Corrupt save file"):
        await manager.acquire(session)

    assert manager._assignments == {}
    # SessionStore should still show WARM
    refetched = await store.get_session(session.id)
    assert refetched.temperature == SessionTemperature.WARM
