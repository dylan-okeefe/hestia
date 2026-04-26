"""Unit tests for CLI meta-commands."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.persistence.trace_store import TraceRecord

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
    from hestia.app import _handle_meta_command

    should_exit, new_session = await _handle_meta_command("/quit", sample_session, store)

    assert should_exit is True
    assert new_session.id == sample_session.id  # Same session


@pytest.mark.asyncio
async def test_meta_command_exit(store, sample_session):
    """/exit should also signal exit."""
    from hestia.app import _handle_meta_command

    should_exit, new_session = await _handle_meta_command("/exit", sample_session, store)

    assert should_exit is True


@pytest.mark.asyncio
async def test_meta_command_help(store, sample_session, capsys):
    """/help should print help and not exit."""
    from hestia.app import _handle_meta_command

    should_exit, new_session = await _handle_meta_command("/help", sample_session, store)

    assert should_exit is False
    assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_meta_command_session(store, sample_session):
    """/session should print session metadata."""
    from hestia.app import _handle_meta_command

    should_exit, new_session = await _handle_meta_command("/session", sample_session, store)

    assert should_exit is False
    assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_meta_command_history_empty(store, sample_session):
    """/history on empty session should print '(empty)'."""
    from hestia.app import _handle_meta_command

    should_exit, new_session = await _handle_meta_command("/history", sample_session, store)

    assert should_exit is False


@pytest.mark.asyncio
async def test_meta_command_reset_creates_new_session_same_user(store):
    """/reset should create a new session for the same user and archive the old one."""
    from hestia.app import _handle_meta_command
    from hestia.core.types import SessionState

    # First create a real session in the database
    session1 = await store.get_or_create_session("cli", "testuser")
    original_id = session1.id
    assert session1.state == SessionState.ACTIVE

    should_exit, new_session = await _handle_meta_command("/reset", session1, store)

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
    from hestia.app import _handle_meta_command

    should_exit, new_session = await _handle_meta_command("/unknown_command", sample_session, store)

    assert should_exit is False
    assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_meta_command_with_whitespace(store, sample_session):
    """Commands with whitespace should be handled."""
    from hestia.app import _handle_meta_command

    should_exit, _ = await _handle_meta_command("  /quit  ", sample_session, store)

    assert should_exit is True


@pytest.mark.asyncio
async def test_meta_command_tokens_no_app(store, sample_session, capsys):
    """/tokens without app should print error."""
    from hestia.app import _handle_meta_command

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store)

    assert should_exit is False


@pytest.mark.asyncio
async def test_meta_command_tokens_no_trace_store(store, sample_session, capsys):
    """/tokens with no trace store should print not available."""
    from hestia.app import _handle_meta_command

    app = MagicMock()
    app.trace_store = None

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app)

    assert should_exit is False
    captured = capsys.readouterr()
    assert "Trace store not available" in captured.out


@pytest.mark.asyncio
async def test_meta_command_tokens_empty(store, sample_session, capsys):
    """/tokens with no traces should print no usage yet."""
    from hestia.app import _handle_meta_command

    app = MagicMock()
    app.trace_store = MagicMock()
    app.trace_store.list_recent = AsyncMock(return_value=[])

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app)

    assert should_exit is False
    captured = capsys.readouterr()
    assert "No token usage recorded for this session yet" in captured.out


@pytest.mark.asyncio
async def test_meta_command_tokens_with_usage(store, sample_session, capsys):
    """/tokens should display formatted token usage."""
    from hestia.app import _handle_meta_command

    trace = TraceRecord(
        id="trace-1",
        session_id=sample_session.id,
        turn_id="turn-1",
        started_at=datetime.now(),
        ended_at=datetime.now(),
        user_input_summary="hello",
        tools_called=[],
        tool_call_count=0,
        delegated=False,
        outcome="success",
        artifact_handles=[],
        prompt_tokens=1234,
        completion_tokens=567,
        reasoning_tokens=None,
        total_duration_ms=1000,
    )

    app = MagicMock()
    app.trace_store = MagicMock()
    app.trace_store.list_recent = AsyncMock(return_value=[trace])

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app)

    assert should_exit is False
    captured = capsys.readouterr()
    assert "Tokens: 1,234 prompt + 567 completion = 1,801 total" in captured.out


@pytest.mark.asyncio
async def test_meta_command_tokens_with_reasoning(store, sample_session, capsys):
    """/tokens should include reasoning tokens when present."""
    from hestia.app import _handle_meta_command

    trace = TraceRecord(
        id="trace-1",
        session_id=sample_session.id,
        turn_id="turn-1",
        started_at=datetime.now(),
        ended_at=datetime.now(),
        user_input_summary="hello",
        tools_called=[],
        tool_call_count=0,
        delegated=False,
        outcome="success",
        artifact_handles=[],
        prompt_tokens=1234,
        completion_tokens=567,
        reasoning_tokens=89,
        total_duration_ms=1000,
    )

    app = MagicMock()
    app.trace_store = MagicMock()
    app.trace_store.list_recent = AsyncMock(return_value=[trace])

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app)

    assert should_exit is False
    captured = capsys.readouterr()
    assert "Tokens: 1,234 prompt + 567 completion (+ 89 reasoning) = 1,890 total" in captured.out
