"""Unit tests for the per-chat settings store (L250)."""

from __future__ import annotations

import pytest

from hestia.persistence.chat_settings import SHOW_THINKING_KEY, ChatSettingsStore
from hestia.persistence.db import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_get_returns_none_when_no_override(db):
    store = ChatSettingsStore(db)
    assert await store.get("telegram", "123", SHOW_THINKING_KEY) is None
    assert await store.get_show_thinking("telegram", "123") is None


@pytest.mark.asyncio
async def test_set_and_get_roundtrip(db):
    store = ChatSettingsStore(db)
    await store.set_show_thinking("telegram", "123", True)
    assert await store.get_show_thinking("telegram", "123") is True
    await store.set_show_thinking("telegram", "123", False)
    assert await store.get_show_thinking("telegram", "123") is False


@pytest.mark.asyncio
async def test_settings_are_scoped_per_chat(db):
    store = ChatSettingsStore(db)
    await store.set_show_thinking("telegram", "123", True)
    assert await store.get_show_thinking("telegram", "456") is None
    assert await store.get_show_thinking("matrix", "123") is None


@pytest.mark.asyncio
async def test_overwrite_updates_value(db):
    store = ChatSettingsStore(db)
    await store.set_show_thinking("telegram", "123", True)
    await store.set_show_thinking("telegram", "123", False)
    value = await store.get("telegram", "123", SHOW_THINKING_KEY)
    assert value == "0"


@pytest.mark.asyncio
async def test_persists_across_store_instances(db):
    """A new store instance over the same DB sees previously written values."""
    first = ChatSettingsStore(db)
    await first.set_show_thinking("telegram", "123", True)

    second = ChatSettingsStore(db)
    assert await second.get_show_thinking("telegram", "123") is True


@pytest.mark.asyncio
async def test_clear_cache_reloads_from_db(db):
    """clear_cache drops cached negatives/positives so a fresh read hits the DB."""
    first = ChatSettingsStore(db)
    second = ChatSettingsStore(db)

    # Negative entry cached in `first`, then written by `second`.
    assert await first.get_show_thinking("telegram", "123") is None
    await second.set_show_thinking("telegram", "123", True)
    assert await first.get_show_thinking("telegram", "123") is None  # still cached

    first.clear_cache()
    assert await first.get_show_thinking("telegram", "123") is True


@pytest.mark.asyncio
async def test_set_updates_cache_immediately(db):
    first = ChatSettingsStore(db)
    await first.set_show_thinking("telegram", "123", True)
    assert await first.get_show_thinking("telegram", "123") is True

    second = ChatSettingsStore(db)
    await second.set_show_thinking("telegram", "123", False)
    # `first` wrote through its own cache; `second` wrote the DB only.
    first.clear_cache()
    assert await first.get_show_thinking("telegram", "123") is False
