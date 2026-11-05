"""Tests for the Telegram /agent per-chat backend switch (L251)."""

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
KIMI_WORKDIR = "/tmp/kimi-workdir"


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
        agent_bridge_enabled=True,
        agent_bridge_chats=[str(OPERATOR), str(GROUP_ID)],
        agent_bridge_kimi_workdir=KIMI_WORKDIR,
    )


@pytest.fixture
def adapter(config: TelegramConfig, store: ChatSettingsStore) -> TelegramAdapter:
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    telegram_adapter.set_agent_bridge(MagicMock())
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
    telegram_adapter: TelegramAdapter,
    user_id: int,
    chat_id: int,
    chat_type: str,
    args: list[str] | None,
) -> str:
    update, reply = _make_update(user_id, chat_id, chat_type)
    context = SimpleNamespace(args=args)
    await telegram_adapter._handle_agent(update, context)
    assert reply.await_count == 1
    return reply.await_args.args[0]


# --- Reporting and switching ---


@pytest.mark.asyncio
async def test_bare_command_reports_default_pi(adapter, store):
    text = await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, None)
    assert text == "Agent backend for this chat: pi. Switch with /agent pi or /agent kimi."
    assert await store.get_agent_backend("telegram", str(OPERATOR)) is None


@pytest.mark.asyncio
async def test_set_kimi_persists_and_confirms(adapter, store):
    text = await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["kimi"])
    assert text == "Agent backend for this chat: kimi."
    assert await store.get_agent_backend("telegram", str(OPERATOR)) == "kimi"


@pytest.mark.asyncio
async def test_set_pi_persists_and_confirms(adapter, store):
    await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["kimi"])
    text = await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["pi"])
    assert text == "Agent backend for this chat: pi."
    assert await store.get_agent_backend("telegram", str(OPERATOR)) == "pi"


@pytest.mark.asyncio
async def test_report_reflects_stored_backend(adapter, store):
    await store.set_agent_backend("telegram", str(OPERATOR), "kimi")
    text = await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, None)
    assert "kimi" in text


@pytest.mark.asyncio
async def test_invalid_argument_replies_usage_and_preserves_setting(adapter, store):
    text = await _run(adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["banana"])
    assert "Usage" in text
    assert await store.get_agent_backend("telegram", str(OPERATOR)) is None


# --- Group chats operate on the chat id ---


@pytest.mark.asyncio
async def test_group_chat_setting_is_keyed_by_chat_id(adapter, store):
    text = await _run(adapter, OPERATOR, GROUP_ID, Chat.SUPERGROUP, ["kimi"])
    assert text == "Agent backend for this chat: kimi."
    assert await store.get_agent_backend("telegram", str(GROUP_ID)) == "kimi"
    assert await store.get_agent_backend("telegram", str(OPERATOR)) is None


# --- Operator gating ---


@pytest.mark.asyncio
async def test_non_operator_is_refused(config, store):
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    telegram_adapter.set_agent_bridge(MagicMock())
    text = await _run(telegram_adapter, OTHER_USER, OTHER_USER, Chat.PRIVATE, ["kimi"])
    assert text == "Not authorized."
    assert await store.get_agent_backend("telegram", str(OTHER_USER)) is None


@pytest.mark.asyncio
async def test_non_operator_in_group_is_silently_ignored(config, store):
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    telegram_adapter.set_agent_bridge(MagicMock())
    update, reply = _make_update(OTHER_USER, GROUP_ID, Chat.SUPERGROUP)
    await telegram_adapter._handle_agent(update, SimpleNamespace(args=["kimi"]))
    reply.assert_not_awaited()
    assert await store.get_agent_backend("telegram", str(GROUP_ID)) is None


# --- Mode and availability gating ---


@pytest.mark.asyncio
async def test_serve_mode_replies_coder_bot_only(config, store):
    telegram_adapter = TelegramAdapter(config)  # no bridge attached
    telegram_adapter.set_chat_settings_store(store)
    text = await _run(telegram_adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["kimi"])
    assert "coder-bot" in text
    assert await store.get_agent_backend("telegram", str(OPERATOR)) is None


@pytest.mark.asyncio
async def test_kimi_unavailable_when_workdir_unset(config, store):
    config.agent_bridge_kimi_workdir = ""
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    telegram_adapter.set_agent_bridge(MagicMock())
    text = await _run(telegram_adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["kimi"])
    assert "not configured" in text
    assert await store.get_agent_backend("telegram", str(OPERATOR)) is None


@pytest.mark.asyncio
async def test_missing_store_reports_unavailable(config):
    telegram_adapter = TelegramAdapter(config)  # no store injected
    telegram_adapter.set_agent_bridge(MagicMock())
    text = await _run(telegram_adapter, OPERATOR, OPERATOR, Chat.PRIVATE, ["pi"])
    assert "not available" in text.lower()


@pytest.mark.asyncio
async def test_operator_unset_denies_everyone(config, store):
    config.operator_user_id = ""
    telegram_adapter = TelegramAdapter(config)
    telegram_adapter.set_chat_settings_store(store)
    telegram_adapter.set_agent_bridge(MagicMock())
    update, reply = _make_update(OPERATOR, OPERATOR, Chat.PRIVATE)
    await telegram_adapter._handle_agent(update, SimpleNamespace(args=["kimi"]))
    assert reply.await_args.args[0] == "Not authorized."
    assert await store.get_agent_backend("telegram", str(OPERATOR)) is None
