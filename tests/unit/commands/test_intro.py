"""Unit tests for the /intro detailed walkthrough command."""

from __future__ import annotations

from datetime import datetime

import pytest

from hestia.commands.intro import (
    INTRO_STEPS,
    IntroStore,
    get_intro_store,
    render_continue,
    render_end,
    render_intro_continue,
    render_intro_end,
    render_intro_start,
)
from hestia.commands.meta import get_default_registry
from hestia.commands.tour import TourStore
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
        id="test_intro_session",
        platform="cli",
        platform_user="intro_user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.fixture
def intro_store():
    """Return a fresh intro store for isolated tests."""
    return IntroStore()


@pytest.fixture
def tour_store():
    """Return a fresh tour store for isolated tests."""
    return TourStore()


# --- Core walkthrough behavior (render level) ---


def test_intro_start_shows_step_one(intro_store):
    text = render_intro_start(intro_store, "cli", "user1")
    assert "Intro step 1 of" in text
    assert intro_store.get("cli", "user1") == 1


def test_intro_continue_walks_every_step(intro_store):
    render_intro_start(intro_store, "cli", "user1")
    seen = 1
    while True:
        text = render_intro_continue(intro_store, "cli", "user1")
        if "Intro complete." in text:
            break
        seen += 1
        assert f"Intro step {seen} of {len(INTRO_STEPS)}" in text
    assert seen == len(INTRO_STEPS)
    assert intro_store.get("cli", "user1") is None


def test_intro_end_clears_cursor(intro_store):
    render_intro_start(intro_store, "cli", "user1")
    assert render_intro_end(intro_store, "cli", "user1") == "Intro ended."
    assert intro_store.get("cli", "user1") is None


def test_intro_end_without_intro_reports_none(intro_store):
    assert render_intro_end(intro_store, "cli", "user1") == "No intro running."


def test_intro_continue_without_intro_reports_none(intro_store):
    assert render_intro_continue(intro_store, "cli", "user1") == "No intro running."


# --- Dispatcher behavior: intro takes precedence, tour still works ---


def test_continue_prefers_active_intro(intro_store, tour_store):
    """With an intro cursor set, /continue advances the intro, not the tour."""
    render_intro_start(intro_store, "cli", "user1")
    text = render_continue(intro_store, tour_store, "cli", "user1")
    assert "Intro step 2 of" in text


def test_continue_falls_back_to_tour(intro_store, tour_store):
    """With no intro cursor, /continue delegates to the tour machinery."""
    from hestia.commands.tour import render_tour_start

    render_tour_start(tour_store, "cli", "user1")
    text = render_continue(intro_store, tour_store, "cli", "user1")
    assert "Step 2 of" in text
    assert "Intro step" not in text


def test_end_prefers_active_intro(intro_store, tour_store):
    render_intro_start(intro_store, "cli", "user1")
    assert render_end(intro_store, tour_store, "cli", "user1") == "Intro ended."
    assert intro_store.get("cli", "user1") is None


# --- Registry-level behavior (shared singleton stores, distinct user key) ---


@pytest.mark.asyncio
async def test_intro_then_continue_walks_every_step(store, sample_session, capsys):
    """/intro then repeated /continue shows every step and ends cleanly."""
    reg = get_default_registry()

    should_exit, _ = await reg.handle("/intro", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Intro step 1 of" in captured.out

    seen_steps = 1
    while True:
        should_exit, _ = await reg.handle("/continue", sample_session, store)
        assert should_exit is False
        captured = capsys.readouterr()
        if "Intro complete." in captured.out:
            break
        seen_steps += 1
        assert f"Intro step {seen_steps} of" in captured.out

    assert seen_steps == len(INTRO_STEPS)

    should_exit, _ = await reg.handle("/continue", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "No tour running" in captured.out

    # Clean up the singleton cursor in case the walkthrough left one behind.
    get_intro_store().clear(sample_session.platform, sample_session.platform_user)


@pytest.mark.asyncio
async def test_endtour_mid_intro_clears_cursor(store, sample_session, capsys):
    """/endtour mid-intro clears the intro cursor."""
    reg = get_default_registry()

    await reg.handle("/intro", sample_session, store)
    assert capsys.readouterr().out

    await reg.handle("/continue", sample_session, store)
    assert capsys.readouterr().out

    should_exit, _ = await reg.handle("/endtour", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "Intro ended" in captured.out

    should_exit, _ = await reg.handle("/continue", sample_session, store)
    assert should_exit is False
    captured = capsys.readouterr()
    assert "No tour running" in captured.out


@pytest.mark.asyncio
async def test_registry_lists_intro(store, sample_session):
    """The /intro command is registered in the default registry."""
    reg = get_default_registry()
    names = [command.name for command in reg.commands()]
    assert "/intro" in names
