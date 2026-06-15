"""Tests for session archival auto-save to memory store."""


import pytest

from hestia.core.types import Message, SessionState, ToolCall
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with a temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()

    store = SessionStore(db)

    yield store
    await db.close()


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_archive_session_with_messages(self, store):
        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session.id, Message(role="user", content="Find me a job")
        )
        await store.append_message(
            session.id, Message(role="assistant", content="Here are some roles...")
        )

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_archive_session_with_no_messages(self, store):
        session = await store.get_or_create_session("cli", "testuser")

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_archive_session_does_not_crash(self, store):
        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session.id, Message(role="user", content="Hello"))
        await store.append_message(
            session.id, Message(role="assistant", content="Hi")
        )

        # Should not raise
        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_create_session_with_archive(self, store):
        session1 = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session1.id, Message(role="user", content="What's the weather?")
        )
        await store.append_message(
            session1.id, Message(role="assistant", content="It's sunny.")
        )

        session2 = await store.create_session(
            "cli", "testuser", archive_previous=session1
        )

        fetched1 = await store.get_session(session1.id)
        assert fetched1.state == SessionState.ARCHIVED

        # New session is active
        assert session2.state == SessionState.ACTIVE

    @pytest.mark.asyncio
    async def test_end_session_archives(self, store):
        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(session.id, Message(role="user", content="Hello"))
        await store.append_message(
            session.id, Message(role="assistant", content="Hi")
        )

        await store.end_session(session.id, "test cleanup")

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_get_active_session_returns_active_or_none(self, store):
        session = await store.get_or_create_session("cli", "testuser")

        active = await store.get_active_session("cli", "testuser")
        assert active is not None
        assert active.id == session.id

        await store.archive_session(session.id)

        active_after_archive = await store.get_active_session("cli", "testuser")
        assert active_after_archive is None

        # Other users are unaffected
        other = await store.get_or_create_session("cli", "otheruser")
        other_active = await store.get_active_session("cli", "otheruser")
        assert other_active is not None
        assert other_active.id == other.id

    @pytest.mark.asyncio
    async def test_tool_call_arguments_non_dict_coerced_on_load(self, store):
        """Legacy/corrupt tool_call arguments that are not dicts become {}."""
        session = await store.get_or_create_session("cli", "testuser")
        await store.append_message(
            session.id,
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id="tc1", name="test_tool", arguments="string-args"),
                    ToolCall(id="tc2", name="test_tool", arguments=None),
                    ToolCall(id="tc3", name="test_tool", arguments=["list-arg"]),
                    ToolCall(id="tc4", name="test_tool", arguments={"ok": True}),
                ],
            ),
        )

        messages = await store.get_messages(session.id)
        assert len(messages) == 1
        loaded = messages[0].tool_calls
        assert loaded is not None
        assert len(loaded) == 4
        assert loaded[0].arguments == {}
        assert loaded[1].arguments == {}
        assert loaded[2].arguments == {}
        assert loaded[3].arguments == {"ok": True}
