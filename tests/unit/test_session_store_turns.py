"""Unit tests for Turn persistence in SessionStore."""

from datetime import datetime

import pytest

from hestia.orchestrator.types import Turn, TurnState, TurnTransition
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


class TestTurnPersistence:
    """Tests for Turn CRUD operations."""

    @pytest.mark.asyncio
    async def test_insert_turn(self, store):
        """Can insert a turn and read it back."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )

        await store.insert_turn(turn)

        # Read it back
        fetched = await store.get_turn("turn_123")
        assert fetched is not None
        assert fetched.id == "turn_123"
        assert fetched.session_id == "session_456"
        assert fetched.state == TurnState.RECEIVED

    @pytest.mark.asyncio
    async def test_update_turn(self, store):
        """Can update a turn's state."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )
        await store.insert_turn(turn)

        # Update the turn
        turn.state = TurnState.DONE
        turn.iterations = 3
        turn.error = None
        await store.update_turn(turn)

        # Read it back
        fetched = await store.get_turn("turn_123")
        assert fetched.state == TurnState.DONE
        assert fetched.iterations == 3

    @pytest.mark.asyncio
    async def test_append_transition(self, store):
        """Can append transitions to a turn."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )
        await store.insert_turn(turn)

        transition = TurnTransition(
            from_state=TurnState.RECEIVED,
            to_state=TurnState.BUILDING_CONTEXT,
            at=datetime.now(),
            note="Starting build",
        )
        await store.append_transition("turn_123", transition)

        # Transitions are stored in DB but not auto-loaded by get_turn
        # Just verify no error was raised

    @pytest.mark.asyncio
    async def test_get_nonexistent_turn(self, store):
        """Getting a nonexistent turn returns None."""
        fetched = await store.get_turn("nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_turns_for_session(self, store):
        """Can list turns for a session."""
        # Create session first
        session = await store.get_or_create_session("test", "user1")

        # Insert some turns
        for i in range(3):
            turn = Turn(
                id=f"turn_{i}",
                session_id=session.id,
                state=TurnState.DONE,
                user_message=None,
                started_at=datetime.now(),
            )
            await store.insert_turn(turn)

        # List turns
        turns = await store.list_turns_for_session(session.id)
        assert len(turns) == 3

    @pytest.mark.asyncio
    async def test_list_turns_respects_limit(self, store):
        """list_turns_for_session respects the limit parameter."""
        session = await store.get_or_create_session("test", "user2")

        # Insert 5 turns
        for i in range(5):
            turn = Turn(
                id=f"turn_{i}",
                session_id=session.id,
                state=TurnState.DONE,
                user_message=None,
                started_at=datetime.now(),
            )
            await store.insert_turn(turn)

        # List with limit
        turns = await store.list_turns_for_session(session.id, limit=2)
        assert len(turns) == 2

    @pytest.mark.asyncio
    async def test_list_turns_filters_by_session(self, store):
        """list_turns_for_session only returns turns for the specified session."""
        session1 = await store.get_or_create_session("test", "user3")
        session2 = await store.get_or_create_session("test", "user4")

        # Insert turns for different sessions
        turn1 = Turn(
            id="turn_a",
            session_id=session1.id,
            state=TurnState.DONE,
            user_message=None,
            started_at=datetime.now(),
        )
        turn2 = Turn(
            id="turn_b",
            session_id=session2.id,
            state=TurnState.DONE,
            user_message=None,
            started_at=datetime.now(),
        )
        await store.insert_turn(turn1)
        await store.insert_turn(turn2)

        # List for session1 only
        turns = await store.list_turns_for_session(session1.id)
        assert len(turns) == 1
        assert turns[0].id == "turn_a"
