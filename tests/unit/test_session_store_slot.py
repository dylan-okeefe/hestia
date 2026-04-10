"""Unit tests for SessionStore slot operations."""


import pytest

from hestia.core.types import SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore


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


class TestSlotOperations:
    """Tests for assign_slot, release_slot, and update_saved_path."""

    @pytest.mark.asyncio
    async def test_assign_slot_makes_hot(self, store):
        """assign_slot sets slot_id and temperature=HOT."""
        session = await store.get_or_create_session("cli", "testuser")
        assert session.temperature == SessionTemperature.COLD
        assert session.slot_id is None

        await store.assign_slot(session.id, slot_id=3)

        fetched = await store.get_session(session.id)
        assert fetched.slot_id == 3
        assert fetched.temperature == SessionTemperature.HOT

    @pytest.mark.asyncio
    async def test_assign_slot_clear_saved_path(self, store):
        """assign_slot with clear_saved_path=True clears slot_saved_path."""
        # First assign and release with a saved path
        session = await store.get_or_create_session("cli", "testuser")
        await store.assign_slot(session.id, slot_id=3)
        await store.release_slot(
            session.id,
            demote_to=SessionTemperature.WARM,
            saved_path="/slots/session.bin",
        )

        # Verify saved_path is set
        fetched = await store.get_session(session.id)
        assert fetched.slot_saved_path == "/slots/session.bin"
        assert fetched.temperature == SessionTemperature.WARM

        # Now re-assign with clear_saved_path
        await store.assign_slot(session.id, slot_id=3, clear_saved_path=True)

        fetched = await store.get_session(session.id)
        assert fetched.slot_id == 3
        assert fetched.slot_saved_path is None  # Cleared!
        assert fetched.temperature == SessionTemperature.HOT

    @pytest.mark.asyncio
    async def test_release_slot_records_saved_path(self, store):
        """release_slot records saved_path when demoting to WARM."""
        session = await store.get_or_create_session("cli", "testuser")
        await store.assign_slot(session.id, slot_id=2)

        await store.release_slot(
            session.id,
            demote_to=SessionTemperature.WARM,
            saved_path="/data/slots/test.bin",
        )

        fetched = await store.get_session(session.id)
        assert fetched.slot_id is None
        assert fetched.temperature == SessionTemperature.WARM
        assert fetched.slot_saved_path == "/data/slots/test.bin"

    @pytest.mark.asyncio
    async def test_release_slot_demotes_to_cold(self, store):
        """release_slot can demote to COLD (no saved path)."""
        session = await store.get_or_create_session("cli", "testuser")
        await store.assign_slot(session.id, slot_id=1)

        await store.release_slot(
            session.id,
            demote_to=SessionTemperature.COLD,
            saved_path=None,
        )

        fetched = await store.get_session(session.id)
        assert fetched.slot_id is None
        assert fetched.temperature == SessionTemperature.COLD
        assert fetched.slot_saved_path is None

    @pytest.mark.asyncio
    async def test_update_saved_path(self, store):
        """update_saved_path sets slot_saved_path without touching other fields."""
        session = await store.get_or_create_session("cli", "testuser")
        await store.assign_slot(session.id, slot_id=5)
        original_temp = SessionTemperature.HOT

        await store.update_saved_path(session.id, "/slots/checkpoint.bin")

        fetched = await store.get_session(session.id)
        assert fetched.slot_saved_path == "/slots/checkpoint.bin"
        assert fetched.slot_id == 5  # Unchanged
        assert fetched.temperature == original_temp  # Unchanged

    @pytest.mark.asyncio
    async def test_slot_round_trip(self, store):
        """Full cycle: assign -> release(saved_path) -> assign(clear_saved_path)."""
        session = await store.get_or_create_session("cli", "testuser")

        # Initial: COLD, no slot
        assert session.temperature == SessionTemperature.COLD
        assert session.slot_id is None

        # Assign slot (becomes HOT)
        await store.assign_slot(session.id, slot_id=0)
        fetched = await store.get_session(session.id)
        assert fetched.temperature == SessionTemperature.HOT
        assert fetched.slot_id == 0
        assert fetched.slot_saved_path is None

        # Release with saved path (becomes WARM)
        await store.release_slot(
            session.id,
            demote_to=SessionTemperature.WARM,
            saved_path="/slots/session_001.bin",
        )
        fetched = await store.get_session(session.id)
        assert fetched.temperature == SessionTemperature.WARM
        assert fetched.slot_id is None
        assert fetched.slot_saved_path == "/slots/session_001.bin"

        # Re-assign, clearing saved path (becomes HOT again)
        await store.assign_slot(session.id, slot_id=1, clear_saved_path=True)
        fetched = await store.get_session(session.id)
        assert fetched.temperature == SessionTemperature.HOT
        assert fetched.slot_id == 1
        assert fetched.slot_saved_path is None
