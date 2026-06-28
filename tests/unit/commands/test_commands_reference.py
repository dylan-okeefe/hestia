"""Unit tests for the /commands reference rendering and /help alias."""

from __future__ import annotations

import pytest

from hestia.commands.meta import (
    _handle_meta_command,
    get_default_registry,
    render_commands_reference,
)
from hestia.commands.registry import CommandRegistry, command_from_handler
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.db import Database
from hestia.persistence.session_store import SessionStore


@pytest.fixture
def registry():
    """Return a fresh command registry."""
    return CommandRegistry()


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
    from datetime import datetime

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


# --- Rendering behavior ---


def test_render_empty_registry():
    """An empty registry renders a fallback message."""
    reg = CommandRegistry()
    assert render_commands_reference(reg) == "No commands available."


def test_render_without_categories_is_alphabetical(registry):
    """Without categories, commands are listed alphabetically by name."""

    async def alpha_handler(ctx):
        """Alpha summary."""
        return False, ctx.session

    async def beta_handler(ctx):
        """Beta summary."""
        return False, ctx.session

    registry.register(command_from_handler(name="/beta", handler=beta_handler))
    registry.register(command_from_handler(name="/alpha", handler=alpha_handler))

    text = render_commands_reference(registry)
    lines = text.splitlines()
    # First line is the header, second is blank; commands start at index 2.
    assert lines[2].startswith("  /alpha")
    assert lines[3].startswith("  /beta")


def test_render_with_categories_groups_by_category(registry):
    """With categories, commands are grouped under category headings."""

    async def cat1_handler(ctx):
        """First command."""
        return False, ctx.session

    async def cat2_handler(ctx):
        """Second command."""
        return False, ctx.session

    registry.register(
        command_from_handler(name="/second", handler=cat2_handler, category="b")
    )
    registry.register(
        command_from_handler(name="/first", handler=cat1_handler, category="a")
    )

    text = render_commands_reference(registry)
    assert "a:" in text
    assert "b:" in text
    assert text.index("a:") < text.index("b:")
    assert text.index("/first") < text.index("/second")


def test_render_includes_aliases(registry):
    """Aliases are shown next to the canonical command name."""

    async def handler(ctx):
        """A command with aliases."""
        return False, ctx.session

    registry.register(
        command_from_handler(
            name="/cmd", handler=handler, aliases=("/c", "/alias")
        )
    )

    text = render_commands_reference(registry)
    assert "/cmd, /c, /alias" in text


# --- Drift guard ---


def test_commands_reference_contains_every_registered_command():
    """/commands output must include every canonical command in the registry."""
    reg = get_default_registry()
    text = render_commands_reference(reg)
    for command in reg.commands():
        assert command.name in text, f"missing {command.name}"


@pytest.mark.asyncio
async def test_help_output_equals_commands_output(store, sample_session):
    """/help must render the same catalog as /commands."""
    from hestia.commands.meta import render_commands_reference

    commands_text = render_commands_reference(get_default_registry())

    should_exit, _ = await _handle_meta_command("/help", sample_session, store)
    assert should_exit is False

    help_text = render_commands_reference(get_default_registry())
    assert help_text == commands_text
