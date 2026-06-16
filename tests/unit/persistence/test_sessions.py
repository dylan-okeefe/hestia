"""Tests for session persistence."""

import pytest

from hestia.core.types import SessionState
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


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


@pytest.fixture
async def message_store(store):
    """Create a MessageStore bound to the same database."""
    return MessageStore(store._db)


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_archive_session(self, store):
        session = await store.get_or_create_session("cli", "testuser")

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED

    @pytest.mark.asyncio
    async def test_create_session_with_archive(self, store):
        session1 = await store.get_or_create_session("cli", "testuser")

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
    async def test_archive_session_bumps_last_active_via_message_store(
        self, store, message_store
    ):
        from hestia.core.types import Message

        session = await store.get_or_create_session("cli", "testuser")
        await message_store.append_message(
            session.id,
            Message(role="user", content="hello"),
        )

        await store.archive_session(session.id)

        fetched = await store.get_session(session.id)
        assert fetched.state == SessionState.ARCHIVED
