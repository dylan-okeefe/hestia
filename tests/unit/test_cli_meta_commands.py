"""Unit tests for CLI meta-commands."""

from datetime import datetime

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore

# Import the handler function - we need to import it from the CLI module
# Since it's an async function inside cli.py, we'll test it directly


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
def sample_session():
    """Create a sample session."""
    return Session(
        id="test_session_123",
        platform="cli",
        platform_user="test_user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.mark.asyncio
async def test_meta_command_quit(store, sample_session, capsys):
    """/quit should signal exit."""
    from hestia.cli import _handle_meta_command

    should_exit, new_session = await _handle_meta_command(
        "/quit", sample_session, store
    )

    assert should_exit is True
    assert new_session.id == sample_session.id  # Same session


@pytest.mark.asyncio
async def test_meta_command_exit(store, sample_session):
    """/exit should also signal exit."""
    from hestia.cli import _handle_meta_command

    should_exit, new_session = await _handle_meta_command(
        "/exit", sample_session, store
    )

    assert should_exit is True


@pytest.mark.asyncio
async def test_meta_command_help(store, sample_session, capsys):
    """/help should print help and not exit."""
    from hestia.cli import _handle_meta_command

    should_exit, new_session = await _handle_meta_command(
        "/help", sample_session, store
    )

    assert should_exit is False
    assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_meta_command_session(store, sample_session):
    """/session should print session metadata."""
    from hestia.cli import _handle_meta_command

    should_exit, new_session = await _handle_meta_command(
        "/session", sample_session, store
    )

    assert should_exit is False
    assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_meta_command_history_empty(store, sample_session):
    """/history on empty session should print '(empty)'."""
    from hestia.cli import _handle_meta_command

    should_exit, new_session = await _handle_meta_command(
        "/history", sample_session, store
    )

    assert should_exit is False


@pytest.mark.asyncio
async def test_meta_command_reset_creates_new_session_same_user(store):
    """/reset should create a new session for the same user and archive the old one."""
    from hestia.cli import _handle_meta_command
    from hestia.core.types import SessionState

    # First create a real session in the database
    session1 = await store.get_or_create_session("cli", "testuser")
    original_id = session1.id
    assert session1.state == SessionState.ACTIVE

    should_exit, new_session = await _handle_meta_command(
        "/reset", session1, store
    )

    assert should_exit is False
    assert new_session.id != original_id  # New session ID
    assert new_session.platform == session1.platform  # Same platform
    assert new_session.platform_user == session1.platform_user  # Same user!

    # Old session should be archived
    fetched_old = await store.get_session(original_id)
    assert fetched_old.state == SessionState.ARCHIVED

    # New session should be active
    assert new_session.state == SessionState.ACTIVE


@pytest.mark.asyncio
async def test_meta_command_unknown(store, sample_session):
    """Unknown commands should print error and not exit."""
    from hestia.cli import _handle_meta_command

    should_exit, new_session = await _handle_meta_command(
        "/unknown_command", sample_session, store
    )

    assert should_exit is False
    assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_meta_command_with_whitespace(store, sample_session):
    """Commands with whitespace should be handled."""
    from hestia.cli import _handle_meta_command

    should_exit, _ = await _handle_meta_command(
        "  /quit  ", sample_session, store
    )

    assert should_exit is True
