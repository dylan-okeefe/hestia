"""Unit tests for the command registry and migrated meta-commands."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.commands.meta import _handle_meta_command, get_default_registry
from hestia.commands.registry import (
    CommandRegistry,
    RegistryValidationError,
    command_from_handler,
    validate_registry,
)
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore
from hestia.persistence.trace_store import TraceRecord


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with a temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    session_store = SessionStore(db)
    yield session_store
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


@pytest.fixture
def registry():
    """Return a fresh command registry."""
    return CommandRegistry()


# --- Registry introspection ---


def test_registry_exposes_command_metadata(registry):
    """Registered commands expose name, aliases, summary, and long help."""

    async def handler(ctx):
        """One-line summary.

        Extended description spans multiple lines.
        """
        return False, ctx.session

    registry.register(
        command_from_handler(
            name="/demo", handler=handler, aliases=("/d",), category="test"
        )
    )

    command = registry.get("/demo")
    assert command is not None
    assert command.name == "/demo"
    assert command.aliases == ("/d",)
    assert command.summary == "One-line summary."
    assert "Extended description" in command.long_help
    assert command.category == "test"

    # Aliases resolve to the same command.
    assert registry.get("/d") is command
    assert registry.get("/DEMO") is command


def test_registry_lookup_unknown_returns_none(registry):
    """Unknown commands do not resolve."""
    assert registry.get("/nope") is None


def test_registry_register_duplicate_rejects(registry):
    """Registering a duplicate name or alias raises."""

    async def handler(ctx):
        """Handler."""
        return False, ctx.session

    registry.register(command_from_handler(name="/a", handler=handler))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(command_from_handler(name="/a", handler=handler))

    registry.register(command_from_handler(name="/b", handler=handler, aliases=("/c",)))
    with pytest.raises(ValueError, match="conflicts"):
        registry.register(command_from_handler(name="/d", handler=handler, aliases=("/c",)))


# --- Docstring lint/drift gate ---


async def _undocumented_handler(ctx):
    return False, ctx.session


def test_validate_registry_rejects_missing_docstring(registry):
    """Commands without docstrings fail the lint check."""
    registry.register(command_from_handler(name="/bad", handler=_undocumented_handler))
    with pytest.raises(RegistryValidationError, match="missing a summary"):
        validate_registry(registry)


def test_validate_registry_accepts_documented_commands(registry):
    """Documented commands pass the lint check."""

    async def handler(ctx):
        """A documented command."""
        return False, ctx.session

    registry.register(command_from_handler(name="/good", handler=handler))
    validate_registry(registry)  # does not raise


# --- Default registry coverage ---


def test_default_registry_has_expected_commands():
    """The default registry contains every migrated meta-command."""
    reg = get_default_registry()
    names = {cmd.name for cmd in reg.commands()}
    expected = {
        "/quit",
        "/reset",
        "/compact",
        "/history",
        "/session",
        "/refresh",
        "/tokens",
        "/commands",
    }
    assert expected <= names
    assert reg.get("/exit") is reg.get("/quit")
    assert reg.get("/help") is reg.get("/commands")


def test_default_registry_passes_validation():
    """All migrated commands have docstrings."""
    validate_registry(get_default_registry())


# --- Behavior parity with legacy _handle_meta_command ---


@pytest.mark.asyncio
async def test_command_quit_and_exit_resolve_and_exit(store, sample_session):
    """/quit and /exit signal exit through the registry."""
    reg = get_default_registry()

    for cmd in ("/quit", "/exit", "  /quit  ", "/QUIT"):
        should_exit, new_session = await reg.handle(cmd, sample_session, store)
        assert should_exit is True
        assert new_session.id == sample_session.id


@pytest.mark.asyncio
async def test_command_help_lists_all_commands(store, sample_session, capsys):
    """/help prints every registered command."""
    should_exit, _ = await _handle_meta_command("/help", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Available commands:" in captured.out
    for name in ("/quit", "/reset", "/compact", "/history", "/session", "/refresh", "/tokens", "/commands"):
        assert name in captured.out
    assert "/help" in captured.out


@pytest.mark.asyncio
async def test_command_session_prints_metadata(store, sample_session, capsys):
    """/session prints session metadata."""
    should_exit, _ = await _handle_meta_command("/session", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Session ID: test_session_123" in captured.out
    assert "Temperature: cold" in captured.out


@pytest.mark.asyncio
async def test_command_session_with_slot_and_budget(store, sample_session, capsys):
    """/session shows slot and budget info when available."""
    sample_session.slot_id = 7
    sample_session.slot_saved_path = "/tmp/slot.json"

    app_mock = MagicMock()
    app_mock.policy = MagicMock()
    app_mock.policy.ctx_window = 16384
    app_mock.policy.turn_token_budget.return_value = 4096

    should_exit, _ = await _handle_meta_command(
        "/session", sample_session, store, app=app_mock
    )
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Slot ID: 7" in captured.out
    assert "Slot path: /tmp/slot.json" in captured.out
    assert "Context window: 16384 tokens" in captured.out
    assert "Turn budget: 4096 tokens" in captured.out


@pytest.mark.asyncio
async def test_command_history_empty(store, sample_session, capsys):
    """/history on an empty session prints '(empty)'."""
    message_store = MessageStore(store._db)
    should_exit, _ = await _handle_meta_command(
        "/history", sample_session, store, message_store
    )
    assert should_exit is False
    captured = capsys.readouterr()
    assert "(empty)" in captured.out


@pytest.mark.asyncio
async def test_command_compact_with_instruction(store, sample_session, capsys):
    """/compact passes the trailing instruction to the compactor."""
    outcome = MagicMock()
    outcome.message = "Compacted with instruction."

    compactor = AsyncMock()
    compactor.compact = AsyncMock(return_value=outcome)

    app_mock = MagicMock()
    app_mock.compactor = compactor

    should_exit, _ = await _handle_meta_command(
        "/compact keep the job criteria", sample_session, store, app=app_mock
    )
    assert should_exit is False
    compactor.compact.assert_awaited_once_with(
        sample_session.id, instruction="keep the job criteria"
    )
    captured = capsys.readouterr()
    assert "Compacting session..." in captured.out
    assert "Compacted with instruction." in captured.out


@pytest.mark.asyncio
async def test_command_compact_unavailable(store, sample_session, capsys):
    """/compact reports unavailability when the compactor is missing."""
    should_exit, _ = await _handle_meta_command("/compact", sample_session, store, app=None)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Compaction is not available right now" in captured.out


@pytest.mark.asyncio
async def test_command_reset_creates_new_session_and_archives_old(store):
    """/reset creates a new session for the same user and archives the old one."""
    from hestia.core.types import SessionState

    session1 = await store.get_or_create_session("cli", "testuser")
    original_id = session1.id
    assert session1.state == SessionState.ACTIVE

    should_exit, new_session = await _handle_meta_command("/reset", session1, store)

    assert should_exit is False
    assert new_session.id != original_id
    assert new_session.platform == session1.platform
    assert new_session.platform_user == session1.platform_user

    fetched_old = await store.get_session(original_id)
    assert fetched_old.state == SessionState.ARCHIVED
    assert new_session.state == SessionState.ACTIVE


@pytest.mark.asyncio
async def test_command_refresh_with_app(store, sample_session, capsys):
    """/refresh refreshes the memory epoch when app is available."""
    app_mock = MagicMock()
    app_mock.compactor = None

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "hestia.persistence.memory_epochs._compile_and_set_memory_epoch",
            AsyncMock(return_value=True),
        )
        should_exit, _ = await _handle_meta_command(
            "/refresh", sample_session, store, app=app_mock
        )

    assert should_exit is False
    captured = capsys.readouterr()
    assert "Memory epoch refreshed." in captured.out


@pytest.mark.asyncio
async def test_command_refresh_without_app(store, sample_session, capsys):
    """/refresh reports missing app context."""
    should_exit, _ = await _handle_meta_command("/refresh", sample_session, store, app=None)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Cannot refresh: app context not available" in captured.out


@pytest.mark.asyncio
async def test_command_tokens_no_app(store, sample_session, capsys):
    """/tokens without app prints an error."""
    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app=None)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Cannot show tokens: app context not available" in captured.out


@pytest.mark.asyncio
async def test_command_tokens_no_trace_store(store, sample_session, capsys):
    """/tokens reports when the trace store is unavailable."""
    app = MagicMock()
    app.trace_store = None

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app=app)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Trace store not available" in captured.out


@pytest.mark.asyncio
async def test_command_tokens_empty(store, sample_session, capsys):
    """/tokens with no traces reports no usage yet."""
    app = MagicMock()
    app.trace_store = MagicMock()
    app.trace_store.list_recent = AsyncMock(return_value=[])

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app=app)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "No token usage recorded for this session yet" in captured.out


@pytest.mark.asyncio
async def test_command_tokens_with_usage(store, sample_session, capsys):
    """/tokens displays formatted token usage."""
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

    should_exit, _ = await _handle_meta_command("/tokens", sample_session, store, app=app)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Tokens: 1,234 prompt + 567 completion = 1,801 total" in captured.out


@pytest.mark.asyncio
async def test_command_unknown(store, sample_session, capsys):
    """Unknown commands fall through with the legacy message."""
    should_exit, new_session = await _handle_meta_command(
        "/unknown_command", sample_session, store
    )
    assert should_exit is False
    assert new_session.id == sample_session.id
    captured = capsys.readouterr()
    assert "Unknown command: /unknown_command" in captured.out
    assert "Type /help for a list" in captured.out


@pytest.mark.asyncio
async def test_command_unknown_via_registry(store, sample_session, capsys):
    """The registry echoes the same unknown-command message for fallthroughs."""
    reg = get_default_registry()
    should_exit, new_session = await reg.handle("/not-real", sample_session, store)
    assert should_exit is False
    assert new_session.id == sample_session.id
    captured = capsys.readouterr()
    assert "Unknown command: /not-real" in captured.out
