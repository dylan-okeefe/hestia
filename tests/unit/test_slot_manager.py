"""Unit tests for SlotManager."""

from typing import Any

import pytest

from hestia.core.types import ChatResponse, SessionTemperature
from hestia.inference import SlotManager
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore


class FakeInferenceClient:
    """Fake inference client that records slot operations."""

    def __init__(self):
        self.model_name = "fake-model"
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._saved_paths: dict[int, str] = {}  # slot_id -> path

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

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
    # Filename is derived from session.id (sanitized), not from the DB's
    # stored saved_path value.
    expected_filename = f"{session.id}.bin"
    assert inference.calls == [("slot_restore", (0, expected_filename))]

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


@pytest.mark.asyncio
async def test_slot_save_sends_basename_only(store, slot_dir):
    """slot_save receives only the basename, never an absolute path."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    await manager.acquire(session)
    session = await store.get_session(session.id)

    inference.calls.clear()
    await manager.save(session)

    assert len(inference.calls) == 1
    call_name, (slot_id, filename) = inference.calls[0]
    assert call_name == "slot_save"
    assert "/" not in filename
    assert filename.endswith(".bin")


@pytest.mark.asyncio
async def test_slot_restore_derives_filename_from_session_id(store, slot_dir):
    """Restore derives filename from session.id (sanitized), ignoring the
    DB's stored `slot_saved_path` contents.

    This self-heals legacy rows that may hold absolute paths or values with
    characters llama.cpp rejects (e.g. Matrix `!room:server.org`).
    """
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    await store.assign_slot(session.id, slot_id=0)
    # Seed the DB with a poisoned legacy absolute path — restore must ignore
    # it and derive the filename from session.id instead.
    await store.release_slot(
        session.id,
        demote_to=SessionTemperature.WARM,
        saved_path="/old/abs/path/session_x.bin",
    )

    session = await store.get_session(session.id)
    assignment = await manager.acquire(session)

    assert assignment.restored_from_disk is True
    expected_filename = f"{session.id}.bin"
    assert inference.calls == [("slot_restore", (0, expected_filename))]
    assert "/" not in inference.calls[0][1][1]


@pytest.mark.asyncio
async def test_evict_stores_basename_in_db(store, slot_dir):
    """After eviction, the DB holds a basename, not an absolute path."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=1,
    )

    session_a = await store.get_or_create_session("cli", "user1")
    await manager.acquire(session_a)
    session_a = await store.get_session(session_a.id)
    await manager.save(session_a)

    # Evict A by acquiring B
    session_b = await store.get_or_create_session("cli", "user2")
    await manager.acquire(session_b)

    fetched_a = await store.get_session(session_a.id)
    assert fetched_a.temperature == SessionTemperature.WARM
    assert fetched_a.slot_saved_path is not None
    assert "/" not in fetched_a.slot_saved_path
    assert fetched_a.slot_saved_path.endswith(".bin")


@pytest.mark.asyncio
async def test_update_saved_path_stores_basename(store, slot_dir):
    """After save(), update_saved_path stores the basename in the DB."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session("cli", "user1")
    await manager.acquire(session)
    session = await store.get_session(session.id)

    await manager.save(session)

    fetched = await store.get_session(session.id)
    assert fetched.slot_saved_path is not None
    assert "/" not in fetched.slot_saved_path
    assert fetched.slot_saved_path.endswith(".bin")


def test_sanitize_slot_filename_matrix_room_id():
    """Matrix room IDs contain `!` and `:` which llama.cpp rejects."""
    from hestia.inference.slot_manager import _sanitize_slot_filename

    raw = "matrix_!FlnJLehKjOiKBdEmTn:matrix.org_20260417173312_4a303ebb"
    clean = _sanitize_slot_filename(raw)
    assert "!" not in clean
    assert ":" not in clean
    assert clean == "matrix__FlnJLehKjOiKBdEmTn_matrix.org_20260417173312_4a303ebb"


def test_sanitize_slot_filename_leaves_safe_chars_alone():
    """Telegram-style IDs are already safe: `[A-Za-z0-9._-]` is preserved."""
    from hestia.inference.slot_manager import _sanitize_slot_filename

    raw = "telegram_8550496999_20260417173312_abcd.suffix-1"
    assert _sanitize_slot_filename(raw) == raw


def test_sanitize_slot_filename_replaces_path_separators_and_unicode():
    from hestia.inference.slot_manager import _sanitize_slot_filename

    assert _sanitize_slot_filename("a/b\\c d") == "a_b_c_d"
    assert _sanitize_slot_filename("user_\u00e9") == "user__"  # accented char → _


@pytest.mark.asyncio
async def test_save_sanitizes_matrix_room_id_in_filename(store, slot_dir):
    """Save against a Matrix-shaped session.id sends a llama.cpp-safe filename."""
    inference = FakeInferenceClient()
    manager = SlotManager(
        inference=inference,
        session_store=store,
        slot_dir=slot_dir,
        pool_size=4,
    )

    session = await store.get_or_create_session(
        "matrix", "!FlnJLehKjOiKBdEmTn:matrix.org"
    )
    await manager.acquire(session)
    session = await store.get_session(session.id)

    await manager.save(session)

    save_calls = [c for c in inference.calls if c[0] == "slot_save"]
    assert len(save_calls) == 1
    _, (slot_id, filename) = save_calls[0]
    assert "!" not in filename
    assert ":" not in filename
    assert "/" not in filename
    assert filename.endswith(".bin")

    fetched = await store.get_session(session.id)
    assert fetched.slot_saved_path == filename
