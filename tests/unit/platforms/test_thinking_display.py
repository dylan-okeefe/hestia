"""Unit tests for the per-chat thinking display gate and operator default (L250)."""

from __future__ import annotations

import pytest

from hestia.persistence.chat_settings import ChatSettingsStore
from hestia.persistence.db import Database
from hestia.platforms.thinking_display import (
    default_show_thinking,
    make_thinking_display_gate,
    resolve_show_thinking,
)

OPERATOR = "90001"
OTHER_USER = "90002"


@pytest.fixture
async def store(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.connect()
    await db.create_tables()
    yield ChatSettingsStore(db)
    await db.close()


# --- Operator default ---


def test_default_show_thinking_for_operator_chat():
    assert default_show_thinking(OPERATOR, OPERATOR) is True


def test_default_hide_thinking_for_other_users():
    assert default_show_thinking(OTHER_USER, OPERATOR) is False


def test_default_hide_thinking_when_no_operator_configured():
    assert default_show_thinking(OPERATOR, "") is False


def test_default_hide_thinking_for_group_chat_ids():
    """Group chat ids never equal the operator user id, so groups default hidden."""
    assert default_show_thinking("-1001234567890", OPERATOR) is False


# --- resolve_show_thinking ---


@pytest.mark.asyncio
async def test_resolve_returns_stored_override(store):
    await store.set_show_thinking("telegram", OPERATOR, False)
    assert await resolve_show_thinking(store, "telegram", OPERATOR, OPERATOR) is False

    await store.set_show_thinking("telegram", OTHER_USER, True)
    assert await resolve_show_thinking(store, "telegram", OTHER_USER, OPERATOR) is True


@pytest.mark.asyncio
async def test_resolve_falls_back_to_operator_default(store):
    assert await resolve_show_thinking(store, "telegram", OPERATOR, OPERATOR) is True
    assert await resolve_show_thinking(store, "telegram", OTHER_USER, OPERATOR) is False


# --- make_thinking_display_gate ---


@pytest.mark.asyncio
async def test_gate_uses_operator_default_for_telegram(store):
    gate = make_thinking_display_gate(store, OPERATOR)
    assert await gate("telegram", OPERATOR) is True
    assert await gate("telegram", OTHER_USER) is False


@pytest.mark.asyncio
async def test_gate_respects_stored_override(store):
    gate = make_thinking_display_gate(store, OPERATOR)
    await store.set_show_thinking("telegram", OPERATOR, False)
    await store.set_show_thinking("telegram", OTHER_USER, True)
    assert await gate("telegram", OPERATOR) is False
    assert await gate("telegram", OTHER_USER) is True


@pytest.mark.asyncio
async def test_gate_passes_through_non_telegram_platforms(store):
    """Matrix/CLI are out of scope: the gate never hides reasoning for them."""
    gate = make_thinking_display_gate(store, OPERATOR)
    assert await gate("matrix", OPERATOR) is True
    assert await gate("matrix", "!room:example.org") is True
    assert await gate("cli", "default") is True
