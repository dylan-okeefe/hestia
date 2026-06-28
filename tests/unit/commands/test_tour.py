"""Unit tests for the /tour narrated walkthrough commands."""

from __future__ import annotations

from datetime import datetime

import pytest

from hestia.commands.meta import _handle_meta_command, get_default_registry
from hestia.commands.tour import (
    TOUR_STEPS,
    TourStore,
    render_tour_continue,
    render_tour_end,
    render_tour_start,
    tour_capability_coverage,
    tour_command_coverage,
    validate_tour_coverage,
)
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.session_store import SessionStore


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
def tour_store():
    """Return a fresh tour store for isolated tests."""
    return TourStore()


# --- Core walkthrough behavior ---


@pytest.mark.asyncio
async def test_tour_then_continue_walks_every_step_and_terminates(
    store, sample_session, capsys
):
    """/tour then repeated /continue shows every step and ends cleanly."""
    reg = get_default_registry()

    # Start the tour
    should_exit, _ = await reg.handle("/tour", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Step 1 of" in captured.out
    assert "Welcome to the Hestia tour" in captured.out

    # Continue through remaining steps
    seen_steps = 1
    while True:
        should_exit, _ = await reg.handle("/continue", sample_session, store)
        assert should_exit is False
        captured = capsys.readouterr()
        if "Tour complete." in captured.out:
            break
        seen_steps += 1
        assert f"Step {seen_steps} of" in captured.out

    assert seen_steps == len(TOUR_STEPS)

    # A later /continue reports no active tour
    should_exit, _ = await reg.handle("/continue", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "No tour running" in captured.out


@pytest.mark.asyncio
async def test_endtour_mid_tour_clears_cursor(store, sample_session, capsys):
    """/endtour mid-tour clears the cursor; later /continue reports no tour."""
    reg = get_default_registry()

    await reg.handle("/tour", sample_session, store)
    assert capsys.readouterr().out  # consume output

    await reg.handle("/continue", sample_session, store)
    assert capsys.readouterr().out  # consume output

    should_exit, _ = await reg.handle("/endtour", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Tour ended" in captured.out

    should_exit, _ = await reg.handle("/continue", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "No tour running" in captured.out


@pytest.mark.asyncio
async def test_second_tour_restarts_from_step_one(store, sample_session, capsys):
    """A second /tour restarts from step 1 even when a tour is in progress."""
    reg = get_default_registry()

    await reg.handle("/tour", sample_session, store)
    await reg.handle("/continue", sample_session, store)

    should_exit, _ = await reg.handle("/tour", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Step 1 of" in captured.out
    assert "Welcome to the Hestia tour" in captured.out


# --- Group-room behavior ---


@pytest.mark.asyncio
async def test_tour_in_group_does_not_start(store, sample_session, capsys):
    """/tour in a group room replies DM-only and does not start a tour."""
    should_exit, _ = await _handle_meta_command(
        "/tour", sample_session, store, group_room=True
    )
    assert should_exit is False
    captured = capsys.readouterr()
    assert "direct messages only" in captured.out.lower()


@pytest.mark.asyncio
async def test_continue_and_endtour_in_group_report_no_tour(
    store, sample_session, capsys
):
    """/continue and /endtour in a group behave as outside a tour."""
    for cmd in ("/continue", "/endtour"):
        should_exit, _ = await _handle_meta_command(
            cmd, sample_session, store, group_room=True
        )
        assert should_exit is False
        captured = capsys.readouterr()
        assert "No tour running" in captured.out


# --- State store helpers ---


def test_render_tour_start_starts_at_step_one(tour_store):
    """render_tour_start sets cursor to 1 and returns step 1 text."""
    text = render_tour_start(tour_store, "cli", "user1")
    assert tour_store.get("cli", "user1") == 1
    assert "Step 1 of" in text
    assert "Welcome to the Hestia tour" in text


def test_render_tour_start_in_group_is_refused(tour_store):
    """render_tour_start refuses to start in a group room."""
    text = render_tour_start(tour_store, "telegram", "-100123", group_room=True)
    assert "direct messages only" in text.lower()
    assert tour_store.get("telegram", "-100123") is None


def test_render_tour_continue_advances_cursor(tour_store):
    """render_tour_continue shows the next step and advances the cursor."""
    render_tour_start(tour_store, "cli", "user1")

    for expected_step in range(2, len(TOUR_STEPS) + 1):
        text = render_tour_continue(tour_store, "cli", "user1")
        assert f"Step {expected_step} of" in text
        assert tour_store.get("cli", "user1") == expected_step

    # Next continue ends the tour
    text = render_tour_continue(tour_store, "cli", "user1")
    assert text == "Tour complete."
    assert tour_store.get("cli", "user1") is None


def test_render_tour_continue_without_tour_reports_no_tour(tour_store):
    """render_tour_continue without an active cursor reports no tour."""
    text = render_tour_continue(tour_store, "cli", "user1")
    assert text == "No tour running."


def test_render_tour_end_clears_cursor(tour_store):
    """render_tour_end clears the cursor and confirms."""
    render_tour_start(tour_store, "cli", "user1")
    text = render_tour_end(tour_store, "cli", "user1")
    assert text == "Tour ended."
    assert tour_store.get("cli", "user1") is None


def test_render_tour_end_without_tour_reports_no_tour(tour_store):
    """render_tour_end without an active cursor reports no tour."""
    text = render_tour_end(tour_store, "cli", "user1")
    assert text == "No tour running."


# --- Drift guards ---


def test_tour_covers_every_registry_command():
    """Every canonical command in the registry is mentioned by the tour."""
    reg = get_default_registry()
    command_names = [command.name for command in reg.commands()]
    validate_tour_coverage(command_names)


def test_tour_covers_expected_capabilities():
    """Major capability keywords appear in the tour prose."""
    required = {
        "commands",
        "session",
        "history",
        "reset",
        "memory",
        "compact",
        "tokens",
        "tools",
        "workflows",
        "scheduled",
        "voice",
        "telegram",
        "matrix",
        "cli",
    }
    found = tour_capability_coverage()
    missing = required - found
    assert not missing, f"Missing capability coverage: {missing}"


def test_tour_command_coverage_includes_slash_commands():
    """tour_command_coverage finds the slash commands referenced in steps."""
    coverage = tour_command_coverage()
    assert "/commands" in coverage
    assert "/help" in coverage
    assert "/tour" in coverage
    assert "/continue" in coverage
    assert "/endtour" in coverage
    assert "/reset" in coverage
    assert "/session" in coverage
    assert "/history" in coverage
    assert "/refresh" in coverage
    assert "/compact" in coverage
    assert "/tokens" in coverage
    assert "/quit" in coverage
    assert "/exit" in coverage
