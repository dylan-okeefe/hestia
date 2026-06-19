"""Unit tests for Turn persistence."""

from datetime import datetime

import pytest

from hestia.core.types import SessionState
from hestia.orchestrator.handoff_service import HandoffService
from hestia.orchestrator.mappers import turn_domain_to_dto
from hestia.core.types import Message
from hestia.orchestrator.types import Turn, TurnState, TurnTransition
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore
from hestia.persistence.turn_store import TurnStore


@pytest.fixture
async def db(tmp_path):
    """Create a connected temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    yield db
    await db.close()


@pytest.fixture
async def session_store(db):
    return SessionStore(db)


@pytest.fixture
async def message_store(db):
    return MessageStore(db)


@pytest.fixture
async def turn_store(db):
    return TurnStore(db)


@pytest.fixture
async def handoff_service(session_store, message_store):
    return HandoffService(session_store, message_store)


class TestTurnPersistence:
    """Tests for Turn CRUD operations."""

    @pytest.mark.asyncio
    async def test_insert_turn(self, turn_store):
        """Can insert a turn and read it back."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )

        await turn_store.insert_turn(turn_domain_to_dto(turn))

        # Read it back
        fetched = await turn_store.get_turn("turn_123")
        assert fetched is not None
        assert fetched.id == "turn_123"
        assert fetched.session_id == "session_456"
        assert fetched.state == TurnState.RECEIVED.value

    @pytest.mark.asyncio
    async def test_insert_turn_persists_reasoning_budget(self, turn_store):
        """reasoning_budget is persisted and read back."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
            reasoning_budget=4096,
        )

        await turn_store.insert_turn(turn_domain_to_dto(turn))

        fetched = await turn_store.get_turn("turn_123")
        assert fetched is not None
        assert fetched.reasoning_budget == 4096

    @pytest.mark.asyncio
    async def test_update_turn(self, turn_store):
        """Can update a turn's state."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )
        await turn_store.insert_turn(turn_domain_to_dto(turn))

        # Update the turn
        turn.state = TurnState.DONE
        turn.iterations = 3
        turn.error = None
        await turn_store.update_turn(turn_domain_to_dto(turn))

        # Read it back
        fetched = await turn_store.get_turn("turn_123")
        assert fetched.state == TurnState.DONE.value
        assert fetched.iteration == 3

    @pytest.mark.asyncio
    async def test_append_transition(self, turn_store):
        """Can append transitions to a turn."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )
        await turn_store.insert_turn(turn_domain_to_dto(turn))

        transition = TurnTransition(
            from_state=TurnState.RECEIVED,
            to_state=TurnState.BUILDING_CONTEXT,
            at=datetime.now(),
            note="Starting build",
        )
        from hestia.orchestrator.mappers import turn_transition_domain_to_dto

        await turn_store.append_transition(
            turn_transition_domain_to_dto("turn_123", transition)
        )

        # Transitions are stored in DB but not auto-loaded by get_turn
        # Just verify no error was raised

    @pytest.mark.asyncio
    async def test_get_nonexistent_turn(self, turn_store):
        """Getting a nonexistent turn returns None."""
        fetched = await turn_store.get_turn("nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_turns_for_session(self, turn_store, session_store):
        """Can list turns for a session."""
        # Create session first
        session = await session_store.get_or_create_session("test", "user1")

        # Insert some turns
        for i in range(3):
            turn = Turn(
                id=f"turn_{i}",
                session_id=session.id,
                state=TurnState.DONE,
                user_message=None,
                started_at=datetime.now(),
            )
            await turn_store.insert_turn(turn_domain_to_dto(turn))

        # List turns
        turns = await turn_store.list_turns_for_session(session.id)
        assert len(turns) == 3

    @pytest.mark.asyncio
    async def test_list_turns_respects_limit(self, turn_store, session_store):
        """list_turns_for_session respects the limit parameter."""
        session = await session_store.get_or_create_session("test", "user2")

        # Insert 5 turns
        for i in range(5):
            turn = Turn(
                id=f"turn_{i}",
                session_id=session.id,
                state=TurnState.DONE,
                user_message=None,
                started_at=datetime.now(),
            )
            await turn_store.insert_turn(turn_domain_to_dto(turn))

        # List with limit
        turns = await turn_store.list_turns_for_session(session.id, limit=2)
        assert len(turns) == 2

    @pytest.mark.asyncio
    async def test_list_turns_filters_by_session(self, turn_store, session_store):
        """list_turns_for_session only returns turns for the specified session."""
        session1 = await session_store.get_or_create_session("test", "user3")
        session2 = await session_store.get_or_create_session("test", "user4")

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
        await turn_store.insert_turn(turn_domain_to_dto(turn1))
        await turn_store.insert_turn(turn_domain_to_dto(turn2))

        # List for session1 only
        turns = await turn_store.list_turns_for_session(session1.id)
        assert len(turns) == 1
        assert turns[0].id == "turn_a"

    @pytest.mark.asyncio
    async def test_count_turns_for_sessions(self, turn_store, session_store):
        """count_turns_for_sessions returns correct counts for multiple sessions."""
        session1 = await session_store.get_or_create_session("test", "user5")
        session2 = await session_store.get_or_create_session("test", "user6")

        for i in range(3):
            await turn_store.insert_turn(
                turn_domain_to_dto(
                    Turn(
                        id=f"t1_{i}",
                        session_id=session1.id,
                        state=TurnState.DONE,
                        user_message=None,
                        started_at=datetime.now(),
                    )
                )
            )
        for i in range(5):
            await turn_store.insert_turn(
                turn_domain_to_dto(
                    Turn(
                        id=f"t2_{i}",
                        session_id=session2.id,
                        state=TurnState.DONE,
                        user_message=None,
                        started_at=datetime.now(),
                    )
                )
            )

        counts = await turn_store.count_turns_for_sessions([session1.id, session2.id])
        assert counts[session1.id] == 3
        assert counts[session2.id] == 5

    @pytest.mark.asyncio
    async def test_count_turns_for_sessions_empty(self, turn_store):
        assert await turn_store.count_turns_for_sessions([]) == {}


class TestCreateSession:
    """Tests for create_session method."""

    @pytest.mark.asyncio
    async def test_create_session_with_archive_creates_new(self, session_store):
        """create_session(archive_previous=...) supersedes the old session."""
        session1 = await session_store.get_or_create_session("cli", "testuser")
        original_id = session1.id

        session2 = await session_store.create_session(
            "cli", "testuser", archive_previous=session1
        )

        assert session2.id != original_id
        assert session2.platform == "cli"
        assert session2.platform_user == "testuser"
        assert session2.state == SessionState.ACTIVE

        # Old session row is preserved but ARCHIVED; new session is ACTIVE.
        fetched1 = await session_store.get_session(session1.id)
        fetched2 = await session_store.get_session(session2.id)
        assert fetched1 is not None
        assert fetched2 is not None
        assert fetched1.state == SessionState.ARCHIVED
        assert fetched2.state == SessionState.ACTIVE

    @pytest.mark.asyncio
    async def test_create_session_same_user_new_identity(self, session_store):
        """create_session preserves user identity while creating fresh session."""
        session1 = await session_store.get_or_create_session("matrix", "@user:matrix.org")

        session2 = await session_store.create_session(
            "matrix", "@user:matrix.org", archive_previous=session1
        )

        assert session1.platform_user == session2.platform_user
        assert session1.id != session2.id
        assert session1.platform == session2.platform

    @pytest.mark.asyncio
    async def test_create_session_without_archive_violates_unique_index(self, session_store):
        """create_session(archive_previous=None) for an existing ACTIVE user fails."""
        from sqlalchemy.exc import IntegrityError

        await session_store.get_or_create_session("cli", "duplicate-user")

        with pytest.raises(IntegrityError):
            await session_store.create_session("cli", "duplicate-user")

    @pytest.mark.asyncio
    async def test_create_session_archives_previous(self, session_store):
        """create_session with archive_previous marks old session ARCHIVED."""
        # Create initial session
        session1 = await session_store.get_or_create_session("cli", "testuser")
        assert session1.state == SessionState.ACTIVE

        # Create new session with archive_previous
        session2 = await session_store.create_session(
            "cli", "testuser", archive_previous=session1
        )

        # New session is ACTIVE
        assert session2.state == SessionState.ACTIVE
        assert session2.id != session1.id

        # Old session is now ARCHIVED
        fetched1 = await session_store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_get_or_create_skips_archived(self, session_store):
        """get_or_create_session creates new session if existing is ARCHIVED."""
        # Create and then archive a session
        session1 = await session_store.get_or_create_session("cli", "testuser")
        await session_store.archive_session(session1.id)

        # Verify it's archived
        fetched = await session_store.get_session(session1.id)
        assert fetched.state == SessionState.ARCHIVED

        # get_or_create_session should create a new one, not return archived
        session2 = await session_store.get_or_create_session("cli", "testuser")
        assert session2.id != session1.id
        assert session2.state == SessionState.ACTIVE


class TestArchiveSession:
    """Tests for archive_session method."""

    @pytest.mark.asyncio
    async def test_archive_session_marks_archived(self, session_store):
        """archive_session transitions session to ARCHIVED state."""
        session = await session_store.get_or_create_session("cli", "testuser")
        assert session.state == SessionState.ACTIVE

        await session_store.archive_session(session.id)

        fetched = await session_store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED


class TestSessionHandoff:
    """Tests for session handoff via HandoffService."""

    @pytest.mark.asyncio
    async def test_generate_handoff_creates_handoff_message(
        self, session_store, message_store, handoff_service
    ):
        """generate_handoff_summary archives the session and writes a handoff message."""
        from hestia.core.types import Message

        session = await session_store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            session.id,
            Message(role="user", content="Hello"),
        )
        await message_store.append_message(
            session.id,
            Message(role="assistant", content="Hi"),
        )

        await handoff_service.generate_handoff_summary(session.id, summary="Test summary")

        fetched = await session_store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

        handoffs = await handoff_service.get_recent_handoffs("cli", "testuser")
        assert len(handoffs) == 1
        assert "Test summary" in handoffs[0]["summary"]
        assert session.id in handoffs[0]["session_id"]

    @pytest.mark.asyncio
    async def test_generate_handoff_captures_last_eight_messages(
        self, session_store, message_store, handoff_service
    ):
        """Handoff message contains the last 8 user/assistant messages."""
        from hestia.core.types import Message

        session = await session_store.get_or_create_session("cli", "testuser")
        for i in range(10):
            await message_store.append_message(
                session.id,
                Message(role="user", content=f"Message {i}"),
            )
            await message_store.append_message(
                session.id,
                Message(role="assistant", content=f"Reply {i}"),
            )

        await handoff_service.generate_handoff_summary(session.id)

        handoffs = await handoff_service.get_recent_handoffs("cli", "testuser")
        assert len(handoffs) == 1
        summary = handoffs[0]["summary"]
        assert "Message 6" in summary
        assert "Reply 9" in summary

    @pytest.mark.asyncio
    async def test_get_recent_handoffs_returns_none_when_empty(self, handoff_service):
        """get_recent_handoffs returns empty list if no handoffs exist."""
        handoffs = await handoff_service.get_recent_handoffs("cli", "unknown")
        assert handoffs == []

    @pytest.mark.asyncio
    async def test_get_recent_handoffs_most_recent(
        self, session_store, message_store, handoff_service
    ):
        """get_recent_handoffs returns the most recent handoff."""
        session1 = await session_store.get_or_create_session("cli", "testuser")
        await handoff_service.generate_handoff_summary(session1.id, summary="First")

        session2 = await session_store.get_or_create_session("cli", "testuser")
        await handoff_service.generate_handoff_summary(session2.id, summary="Second")

        handoffs = await handoff_service.get_recent_handoffs("cli", "testuser")
        assert len(handoffs) == 1
        assert "Second" in handoffs[0]["summary"]
        assert session2.id in handoffs[0]["session_id"]

    @pytest.mark.asyncio
    async def test_get_or_create_session_with_handoff_injects_message(
        self, session_store, message_store, handoff_service
    ):
        """get_or_create_session_with_handoff prepends a synthetic handoff message."""
        from hestia.core.types import Message

        # Archive a session with a handoff
        old_session = await session_store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            old_session.id,
            Message(role="user", content="Hello"),
        )
        await handoff_service.generate_handoff_summary(
            old_session.id, summary="Prior context"
        )

        # Create a new session via the handoff-aware path
        new_session = await handoff_service.get_or_create_session_with_handoff(
            "cli", "testuser"
        )
        messages = await message_store.get_messages(new_session.id)

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].is_handoff
        assert "[Previous session context]" in messages[0].content
        assert "Prior context" in messages[0].content
        assert "Hello" in messages[0].content

    @pytest.mark.asyncio
    async def test_get_or_create_session_with_handoff_skips_existing(
        self, session_store, message_store, handoff_service
    ):
        """get_or_create_session_with_handoff does not inject if session already has messages."""
        from hestia.core.types import Message

        # Create and archive an old session with a handoff
        old = await session_store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            old.id,
            Message(role="user", content="Old msg"),
        )
        await handoff_service.generate_handoff_summary(old.id, summary="Old")

        # Create a new session and add a message to it
        new_session = await session_store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            new_session.id,
            Message(role="user", content="First"),
        )

        # Calling get_or_create_session_with_handoff again should return the same
        # active session (it already has messages), so no handoff injection.
        result = await handoff_service.get_or_create_session_with_handoff(
            "cli", "testuser"
        )
        messages = await message_store.get_messages(result.id)
        assert len(messages) == 1
        assert messages[0].content == "First"

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities(
        self, session_store, message_store, handoff_service
    ):
        """list_handoffs_for_identities returns handoffs for multiple identities."""
        from hestia.core.types import Message

        session1 = await session_store.get_or_create_session("cli", "user1")
        await message_store.append_message(
            session1.id,
            Message(role="user", content="Hello"),
        )
        await handoff_service.generate_handoff_summary(session1.id, summary="First handoff")

        session2 = await session_store.get_or_create_session("matrix", "@user:matrix.org")
        await message_store.append_message(
            session2.id,
            Message(role="user", content="Hi"),
        )
        await handoff_service.generate_handoff_summary(session2.id, summary="Second handoff")

        # Query for both identities
        handoffs = await handoff_service.list_handoffs_for_identities(
            [("cli", "user1"), ("matrix", "@user:matrix.org")], limit=3
        )
        assert len(handoffs) == 2
        summaries = [h["summary"] for h in handoffs]
        assert any("First handoff" in s for s in summaries)
        assert any("Second handoff" in s for s in summaries)
        # Should be ordered by created_at desc (most recent first)
        assert "Second handoff" in handoffs[0]["summary"]

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities_empty(self, handoff_service):
        """list_handoffs_for_identities returns empty list for unknown identities."""
        handoffs = await handoff_service.list_handoffs_for_identities(
            [("cli", "unknown")], limit=3
        )
        assert handoffs == []

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities_no_identities(self, handoff_service):
        """list_handoffs_for_identities returns empty list when given no identities."""
        handoffs = await handoff_service.list_handoffs_for_identities([], limit=3)
        assert handoffs == []

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities_respects_limit(
        self, session_store, message_store, handoff_service
    ):
        """list_handoffs_for_identities respects the limit parameter."""
        for i in range(5):
            session = await session_store.get_or_create_session("cli", "user1")
            await message_store.append_message(
                session.id,
                Message(role="user", content=f"Msg {i}"),
            )
            await handoff_service.generate_handoff_summary(
                session.id, summary=f"Handoff {i}"
            )

        handoffs = await handoff_service.list_handoffs_for_identities(
            [("cli", "user1")], limit=2
        )
        assert len(handoffs) == 2

    @pytest.mark.asyncio
    async def test_create_session_with_archive_generates_handoff(
        self, session_store, message_store, handoff_service
    ):
        """create_session with archive_previous archives and callers may generate handoff."""
        from hestia.core.types import Message

        session1 = await session_store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            session1.id,
            Message(role="user", content="Hi"),
        )

        session2 = await session_store.create_session(
            "cli", "testuser", archive_previous=session1
        )

        # Old session archived
        fetched1 = await session_store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

        # Generate handoff explicitly
        await handoff_service.generate_handoff_summary(session1.id)
        handoffs = await handoff_service.get_recent_handoffs("cli", "testuser")
        assert len(handoffs) == 1
        assert session1.id in handoffs[0]["session_id"]

        # New session active
        assert session2.state == SessionState.ACTIVE
