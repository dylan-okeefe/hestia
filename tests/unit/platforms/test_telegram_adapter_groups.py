"""Tests for Telegram group chat routing (L169b)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from telegram import Chat, Message, Update, User

from hestia.config import TelegramConfig
from hestia.platforms.telegram_adapter import TelegramAdapter


@pytest.fixture
def telegram_config() -> TelegramConfig:
    """Default Telegram config for testing."""
    return TelegramConfig(bot_token="test:token12345")


@pytest.fixture
def adapter(telegram_config: TelegramConfig) -> TelegramAdapter:
    """Unstarted TelegramAdapter instance."""
    return TelegramAdapter(telegram_config)


class TestTelegramGroupChatRouting:
    """Tests for group chat sender_platform_user routing."""

    @pytest.mark.asyncio
    async def test_group_chat_passes_sender_platform_user(
        self,
        telegram_config: TelegramConfig,
        adapter: TelegramAdapter,
    ) -> None:
        """In a group chat, sender_platform_user is the individual user ID."""
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)

        received_args: tuple[str, str, str, str | None, str | None] | None = None

        async def on_message(platform: str, user: str, text: str, sender: str | None, session_title: str | None = None) -> None:
            nonlocal received_args
            received_args = (platform, user, text, sender, session_title)

        adapter._on_message = on_message

        # Create mock update for a group chat
        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_chat = MagicMock(spec=Chat)
        mock_chat.id = -1001234567890
        mock_chat.type = Chat.SUPERGROUP
        mock_chat.title = "Test Group"
        mock_update.effective_chat = mock_chat

        mock_message = MagicMock(spec=Message)
        mock_message.text = "Hello group"
        mock_update.effective_message = mock_message

        await adapter._handle_message(mock_update, None)

        assert received_args is not None
        assert received_args[0] == "telegram"
        assert received_args[1] == "-1001234567890"  # chat ID as platform_user
        assert received_args[2] == "Hello group"
        assert received_args[3] == "12345"  # sender_platform_user
        assert received_args[4] == "Test Group"  # session_title from group chat

    @pytest.mark.asyncio
    async def test_private_chat_passes_none_sender(
        self,
        telegram_config: TelegramConfig,
        adapter: TelegramAdapter,
    ) -> None:
        """In a private chat, sender_platform_user is None."""
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)

        received_args: tuple[str, str, str, str | None, str | None] | None = None

        async def on_message(platform: str, user: str, text: str, sender: str | None, session_title: str | None = None) -> None:
            nonlocal received_args
            received_args = (platform, user, text, sender, session_title)

        adapter._on_message = on_message

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_chat = MagicMock(spec=Chat)
        mock_chat.id = 12345
        mock_chat.type = Chat.PRIVATE
        mock_update.effective_chat = mock_chat

        mock_message = MagicMock(spec=Message)
        mock_message.text = "Hello private"
        mock_update.effective_message = mock_message

        await adapter._handle_message(mock_update, None)

        assert received_args is not None
        assert received_args[0] == "telegram"
        assert received_args[1] == "12345"
        assert received_args[2] == "Hello private"
        assert received_args[3] is None
        assert received_args[4] is None  # session_title in private chat

    @pytest.mark.asyncio
    async def test_group_chat_ignores_disallowed_user(
        self,
        telegram_config: TelegramConfig,
        adapter: TelegramAdapter,
    ) -> None:
        """Disallowed users in groups are silently ignored."""
        telegram_config.allowed_users = ["allowed_user"]
        adapter = TelegramAdapter(telegram_config)

        callback_called = False

        async def on_message(platform: str, user: str, text: str, sender: str | None, session_title: str | None = None) -> None:
            nonlocal callback_called
            callback_called = True

        adapter._on_message = on_message

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "unauthorized_user"
        mock_update.effective_user = mock_user

        mock_chat = MagicMock(spec=Chat)
        mock_chat.id = -1001234567890
        mock_chat.type = Chat.GROUP
        mock_update.effective_chat = mock_chat

        mock_message = MagicMock(spec=Message)
        mock_message.text = "Hello"
        mock_update.effective_message = mock_message

        await adapter._handle_message(mock_update, None)

        assert callback_called is False
