"""Unit tests for Turn persistence in SessionStore."""

from datetime import datetime

import pytest

from hestia.core.types import Message, SessionState
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


class TestCreateSession:
    """Tests for create_session method."""

    @pytest.mark.asyncio
    async def test_create_session_with_archive_creates_new(self, store):
        """create_session(archive_previous=...) supersedes the old session."""
        session1 = await store.get_or_create_session("cli", "testuser")
        original_id = session1.id

        # Call create_session with archive_previous to atomically supersede.
        # This is the only safe usage when an ACTIVE session exists for the
        # user — leaving archive_previous=None would create a duplicate ACTIVE
        # row, which the partial unique index ux_sessions_active_user (added
        # in v0.8.0 to fix the get_or_create TOCTOU race) now correctly
        # forbids.
        session2 = await store.create_session("cli", "testuser", archive_previous=session1)

        assert session2.id != original_id
        assert session2.platform == "cli"
        assert session2.platform_user == "testuser"
        assert session2.state == SessionState.ACTIVE

        # Old session row is preserved but ARCHIVED; new session is ACTIVE.
        fetched1 = await store.get_session(session1.id)
        fetched2 = await store.get_session(session2.id)
        assert fetched1 is not None
        assert fetched2 is not None
        assert fetched1.state == SessionState.ARCHIVED
        assert fetched2.state == SessionState.ACTIVE

    @pytest.mark.asyncio
    async def test_create_session_same_user_new_identity(self, store):
        """create_session preserves user identity while creating fresh session."""
        session1 = await store.get_or_create_session("matrix", "@user:matrix.org")

        session2 = await store.create_session(
            "matrix", "@user:matrix.org", archive_previous=session1
        )

        assert session1.platform_user == session2.platform_user
        assert session1.id != session2.id
        assert session1.platform == session2.platform

    @pytest.mark.asyncio
    async def test_create_session_without_archive_violates_unique_index(self, store):
        """create_session(archive_previous=None) for an existing ACTIVE user fails.

        Documents the post-hotfix contract: callers that want a fresh session
        for a user with an existing ACTIVE row MUST pass ``archive_previous``
        so the supersession happens in a single transaction. The partial
        unique index ``ux_sessions_active_user`` rejects the second INSERT
        otherwise.
        """
        from sqlalchemy.exc import IntegrityError

        await store.get_or_create_session("cli", "duplicate-user")

        with pytest.raises(IntegrityError):
            await store.create_session("cli", "duplicate-user")

    @pytest.mark.asyncio
    async def test_create_session_archives_previous(self, store):
        """create_session with archive_previous marks old session ARCHIVED."""
        # Create initial session
        session1 = await store.get_or_create_session("cli", "testuser")
        assert session1.state == SessionState.ACTIVE

        # Create new session with archive_previous
        session2 = await store.create_session("cli", "testuser", archive_previous=session1)

        # New session is ACTIVE
        assert session2.state == SessionState.ACTIVE
        assert session2.id != session1.id

        # Old session is now ARCHIVED
        fetched1 = await store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_get_or_create_skips_archived(self, store):
        """get_or_create_session creates new session if existing is ARCHIVED."""
        # Create and then archive a session
        session1 = await store.get_or_create_session("cli", "testuser")
        await store.archive_session(session1.id)

        # Verify it's archived
        fetched = await store.get_session(session1.id)
        assert fetched.state == SessionState.ARCHIVED

        # get_or_create_session should create a new one, not return archived
        session2 = await store.get_or_create_session("cli", "testuser")
        assert session2.id != session1.id
        assert session2.state == SessionState.ACTIVE


class TestArchiveSession:
    """Tests for archive_session method."""

    @pytest.mark.asyncio
    async def test_archive_session_marks_archived(self, store):
        """archive_session transitions session to ARCHIVED state."""
        session = await store.get_or_create_session("cli", "testuser")
        assert session.state == SessionState.ACTIVE

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED


class TestSessionHandoff:
    """Tests for session handoff persistence and retrieval."""

    @pytest.mark.asyncio
    async def test_archive_session_creates_handoff(self, store):
        """archive_session generates a handoff record."""
        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session.id, Message(role="user", content="Hello"))
        await store.append_message(session.id, Message(role="assistant", content="Hi"))

        await store.archive_session(session.id, summary="Test summary")

        handoff = await store.get_latest_handoff("cli", "testuser")
        assert handoff is not None
        assert handoff.previous_session_id == session.id
        assert handoff.summary == "Test summary"
        assert handoff.platform == "cli"
        assert handoff.platform_user == "testuser"
        assert len(handoff.key_messages) == 2

    @pytest.mark.asyncio
    async def test_archive_session_captures_last_eight_messages(self, store):
        """archive_session only captures the last 8 user/assistant messages."""
        session = await store.get_or_create_session("cli", "testuser")
        for i in range(10):
            await store.append_message(
                session.id, Message(role="user", content=f"Message {i}")
            )
            await store.append_message(
                session.id, Message(role="assistant", content=f"Reply {i}")
            )

        await store.archive_session(session.id)

        handoff = await store.get_latest_handoff("cli", "testuser")
        assert len(handoff.key_messages) == 8
        assert handoff.key_messages[0]["content"] == "Message 6"
        assert handoff.key_messages[-1]["content"] == "Reply 9"

    @pytest.mark.asyncio
    async def test_archive_session_extracts_artifact_handles(self, store):
        """archive_session scans message content for artifact handles."""
        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session.id,
            Message(
                role="assistant",
                content="Result stored as artifact art_a1b2c3d4e5",
            ),
        )

        await store.archive_session(session.id)

        handoff = await store.get_latest_handoff("cli", "testuser")
        assert "art_a1b2c3d4e5" in handoff.artifacts

    @pytest.mark.asyncio
    async def test_get_latest_handoff_returns_none_when_empty(self, store):
        """get_latest_handoff returns None if no handoffs exist."""
        handoff = await store.get_latest_handoff("cli", "unknown")
        assert handoff is None

    @pytest.mark.asyncio
    async def test_get_latest_handoff_most_recent(self, store):
        """get_latest_handoff returns the most recent handoff."""
        session1 = await store.get_or_create_session("cli", "testuser")
        await store.archive_session(session1.id, summary="First")

        session2 = await store.get_or_create_session("cli", "testuser")
        await store.archive_session(session2.id, summary="Second")

        handoff = await store.get_latest_handoff("cli", "testuser")
        assert handoff is not None
        assert handoff.summary == "Second"
        assert handoff.previous_session_id == session2.id

    @pytest.mark.asyncio
    async def test_get_or_create_session_with_handoff_injects_message(self, store):
        """get_or_create_session_with_handoff prepends a synthetic system message."""
        # Archive a session with a handoff
        old_session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(old_session.id, Message(role="user", content="Hello"))
        await store.archive_session(old_session.id, summary="Prior context")

        # Create a new session via the handoff-aware path
        new_session = await store.get_or_create_session_with_handoff("cli", "testuser")
        messages = await store.get_messages(new_session.id)

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert "[Previous session context]" in messages[0].content
        assert "Prior context" in messages[0].content
        assert "Hello" in messages[0].content

    @pytest.mark.asyncio
    async def test_get_or_create_session_with_handoff_skips_existing(self, store):
        """get_or_create_session_with_handoff does not inject if session already has messages."""
        # Create and archive an old session with a handoff
        old = await store.get_or_create_session("cli", "testuser")
        await store.append_message(old.id, Message(role="user", content="Old msg"))
        await store.archive_session(old.id, summary="Old")

        # Create a new session and add a message to it
        new_session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(new_session.id, Message(role="user", content="First"))

        # Calling get_or_create_session_with_handoff again should return the same
        # active session (it already has messages), so no handoff injection.
        result = await store.get_or_create_session_with_handoff("cli", "testuser")
        messages = await store.get_messages(result.id)
        assert len(messages) == 1
        assert messages[0].content == "First"

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities(self, store):
        """list_handoffs_for_identities returns handoffs for multiple identities."""
        # Create sessions and archive them for two different identities
        session1 = await store.get_or_create_session("cli", "user1")
        await store.append_message(session1.id, Message(role="user", content="Hello"))
        await store.archive_session(session1.id, summary="First handoff")

        session2 = await store.get_or_create_session("matrix", "@user:matrix.org")
        await store.append_message(session2.id, Message(role="user", content="Hi"))
        await store.archive_session(session2.id, summary="Second handoff")

        # Query for both identities
        handoffs = await store.list_handoffs_for_identities(
            [("cli", "user1"), ("matrix", "@user:matrix.org")], limit=3
        )
        assert len(handoffs) == 2
        summaries = {h["summary"] for h in handoffs}
        assert "First handoff" in summaries
        assert "Second handoff" in summaries
        # Should be ordered by created_at desc (most recent first)
        assert handoffs[0]["summary"] == "Second handoff"

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities_empty(self, store):
        """list_handoffs_for_identities returns empty list for unknown identities."""
        handoffs = await store.list_handoffs_for_identities(
            [("cli", "unknown")], limit=3
        )
        assert handoffs == []

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities_no_identities(self, store):
        """list_handoffs_for_identities returns empty list when given no identities."""
        handoffs = await store.list_handoffs_for_identities([], limit=3)
        assert handoffs == []

    @pytest.mark.asyncio
    async def test_list_handoffs_for_identities_respects_limit(self, store):
        """list_handoffs_for_identities respects the limit parameter."""
        for i in range(5):
            session = await store.get_or_create_session("cli", "user1")
            await store.append_message(session.id, Message(role="user", content=f"Msg {i}"))
            await store.archive_session(session.id, summary=f"Handoff {i}")

        handoffs = await store.list_handoffs_for_identities(
            [("cli", "user1")], limit=2
        )
        assert len(handoffs) == 2

    @pytest.mark.asyncio
    async def test_create_session_with_archive_generates_handoff(self, store):
        """create_session with archive_previous now calls archive_session and generates handoff."""
        session1 = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session1.id, Message(role="user", content="Hi"))

        session2 = await store.create_session("cli", "testuser", archive_previous=session1)

        # Old session archived
        fetched1 = await store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

        # Handoff generated
        handoff = await store.get_latest_handoff("cli", "testuser")
        assert handoff is not None
        assert handoff.previous_session_id == session1.id

        # New session active
        assert session2.state == SessionState.ACTIVE
