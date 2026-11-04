"""Tests for the Telegram /thinking per-chat display toggle (L250)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, Update, User

from hestia.config import TelegramConfig
from hestia.persistence.chat_settings import ChatSettingsStore
from hestia.persistence.db import Database
from hestia.platforms.telegram_adapter import TelegramAdapter

OPERATOR = 90001
OTHER_USER = 90002
GROUP_ID = -1001234567890


@pytest.fixture
async def store(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await db.connect()
    await db.create_tables()
    yield ChatSettingsStore(db)
    await db.close()


@pytest.fixture
def config() -> TelegramConfig:
    return TelegramConfig(
        bot_token="test:token12345",
        allowed_users=[str(OPERATOR), str(OTHER_USER)],
        operator_user_id=str(OPERATOR),
    )


@pytest.fixture
def adapter(config: TelegramConfig, store: ChatSettingsStore) -> TelegramAdapter:
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    return telegram_adapter


def _make_update(
    user_id: int,
    chat_id: int,
    chat_type: str,
) -> tuple[MagicMock, AsyncMock]:
    """Build a mock Update with an async reply_text capture."""
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = f"user{user_id}"
    update.effective_user = user

    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    chat.type = chat_type
    update.effective_chat = chat

    reply = AsyncMock()
    message = MagicMock(spec=Message)
    message.reply_text = reply
    update.effective_message = message
    return update, reply


async def _run(
    adapter: TelegramAdapter,
    user_id: int,
    chat_id: int,
    chat_type: str,
    args: list[str] | None,
) -> str:
    update, reply = _make_update(user_id, chat_id, chat_type)
    context = SimpleNamespace(args=args)
    await adapter._handle_thinking(update, context)
    assert reply.await_count == 1
    return reply.await_args.args[0]


# --- Toggle behavior ---


@pytest.mark.asyncio
async def test_bare_command_toggles_operator_default_on_to_off(adapter, store):
    # Operator default is "on"; a bare /thinking turns it off.
    text = await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, None)
    assert text == "Thinking display: off for this chat."
    assert await store.get_show_thinking("telegram", str(OPERATOR)) is False


@pytest.mark.asyncio
async def test_bare_command_toggles_other_user_default_off_to_on(adapter, store):
    # Non-operator default is "off"; a bare /thinking turns it on.
    text = await _run(adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, None)
    assert text == "Thinking display: on for this chat."
    assert await store.get_show_thinking("telegram", str(OTHER_USER)) is True


@pytest.mark.asyncio
async def test_explicit_on_and_off(adapter, store):
    text = await _run(adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, ["on"])
    assert text == "Thinking display: on for this chat."
    assert await store.get_show_thinking("telegram", str(OTHER_USER)) is True

    text = await _run(adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, ["off"])
    assert text == "Thinking display: off for this chat."
    assert await store.get_show_thinking("telegram", str(OTHER_USER)) is False


@pytest.mark.asyncio
async def test_bare_command_toggles_back_and_forth(adapter, store):
    await _run(adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, None)
    assert await store.get_show_thinking("telegram", str(OTHER_USER)) is True
    text = await _run(adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, None)
    assert text == "Thinking display: off for this chat."
    assert await store.get_show_thinking("telegram", str(OTHER_USER)) is False


@pytest.mark.asyncio
async def test_invalid_argument_replies_usage_and_preserves_setting(adapter, store):
    text = await _run(adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, ["banana"])
    assert "Usage" in text
    assert await store.get_show_thinking("telegram", str(OTHER_USER)) is None


# --- Group chats operate on the chat id ---


@pytest.mark.asyncio
async def test_group_chat_setting_is_keyed_by_chat_id(adapter, store):
    text = await _run(adapter, OPERATOR, GROUP_ID, Chat.SUPERGROUP, ["on"])
    assert text == "Thinking display: on for this chat."
    # Stored against the group chat id, not the sender's user id.
    assert await store.get_show_thinking("telegram", str(GROUP_ID)) is True
    assert await store.get_show_thinking("telegram", str(OPERATOR)) is None


@pytest.mark.asyncio
async def test_group_chat_bare_toggle_uses_group_default_hidden(adapter, store):
    # Group chat id is not the operator, so the default is hidden → toggle turns on.
    text = await _run(adapter, OPERATOR, GROUP_ID, Chat.SUPERGROUP, None)
    assert text == "Thinking display: on for this chat."
    assert await store.get_show_thinking("telegram", str(GROUP_ID)) is True


# --- Authorization and availability ---


@pytest.mark.asyncio
async def test_unauthorized_user_is_rejected(config, store):
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    update, reply = _make_update(99999, 99999, Chat.PRIVATE)
    await telegram_adapter._handle_thinking(update, SimpleNamespace(args=None))
    assert reply.await_args.args[0] == "Not authorized."
    assert await store.get_show_thinking("telegram", "99999") is None


@pytest.mark.asyncio
async def test_unauthorized_user_in_group_is_silently_ignored(config, store):
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    update, reply = _make_update(99999, GROUP_ID, Chat.SUPERGROUP)
    await telegram_adapter._handle_thinking(update, SimpleNamespace(args=None))
    reply.assert_not_awaited()
    assert await store.get_show_thinking("telegram", str(GROUP_ID)) is None


@pytest.mark.asyncio
async def test_missing_store_reports_unavailable(config):
    telegram_adapter = TelegramAdapter(config)  # no store injected
    text = await _run(telegram_adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["on"])
    assert "not available" in text.lower()
