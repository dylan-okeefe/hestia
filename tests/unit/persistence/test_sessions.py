"""Tests for session archival auto-save to memory store."""


import pytest

from hestia.core.types import Message, SessionState
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
