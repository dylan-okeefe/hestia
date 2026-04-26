"""Unit and async tests for TelegramAdapter.

These tests use pytest-asyncio to test actual async behavior with
mocked python-telegram-bot components.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot, Message, Update, User
from telegram.ext import Application

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


class TestTelegramAdapterBasics:
    """Basic non-async tests for TelegramAdapter."""

    def test_name_is_telegram(self, adapter: TelegramAdapter) -> None:
        assert adapter.name == "telegram"

    def test_requires_bot_token(self) -> None:
        cfg = TelegramConfig(bot_token="")
        with pytest.raises(ValueError, match="bot_token is required"):
            TelegramAdapter(cfg)

    def test_empty_allowed_users_denies_all(self, adapter: TelegramAdapter) -> None:
        assert adapter._is_allowed(12345, "testuser") is False

    def test_allowed_users_by_id(self, telegram_config: TelegramConfig) -> None:
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)
        assert adapter._is_allowed(12345, "testuser") is True
        assert adapter._is_allowed(99999, "other") is False

    def test_allowed_users_by_username(self, telegram_config: TelegramConfig) -> None:
        telegram_config.allowed_users = ["dylan"]
        adapter = TelegramAdapter(telegram_config)
        assert adapter._is_allowed(12345, "dylan") is True
        assert adapter._is_allowed(12345, "other") is False


class TestTelegramAdapterAsync:
    """Async tests for TelegramAdapter using mocked python-telegram-bot."""

    @pytest.mark.asyncio
    async def test_send_message_calls_bot_send(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Mock bot, verify send_message calls bot.send_message(chat_id, text)."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        # Mock message response
        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 42
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app

        result = await adapter.send_message("12345", "Hello, world!")

        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="Hello, world!",
            parse_mode="HTML",
        )
        assert result == "42"

    @pytest.mark.asyncio
    async def test_edit_message_rate_limited(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Send two edits within rate limit window, verify second is delayed."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        # First edit
        start_time = asyncio.get_event_loop().time()
        await adapter.edit_message("12345", "100", "First edit")
        asyncio.get_event_loop().time() - start_time

        # Second edit immediately - should be rate limited
        start_time = asyncio.get_event_loop().time()
        await adapter.edit_message("12345", "100", "Second edit")
        second_edit_time = asyncio.get_event_loop().time() - start_time

        # Second edit should have taken longer due to rate limiting
        # Rate limit is 1.5 seconds by default
        assert second_edit_time >= 1.4  # Allow small timing variance

    @pytest.mark.asyncio
    async def test_handle_message_rejected_for_disallowed_user(
        self,
        adapter: TelegramAdapter,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify unauthorized user gets no response (callback not called)."""
        telegram_config.allowed_users = ["allowed_user"]
        adapter = TelegramAdapter(telegram_config)

        # Create mock update for disallowed user
        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "unauthorized_user"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.text = "Hello"
        mock_update.effective_message = mock_message

        # Mock reply_text to verify it's called with "Not authorized"
        mock_message.reply_text = AsyncMock()

        # Track if on_message callback is called
        callback_called = False

        async def on_message(platform: str, user: str, text: str) -> None:
            nonlocal callback_called
            callback_called = True

        adapter._on_message = on_message

        await adapter._handle_message(mock_update, None)

        # Callback should NOT be called for disallowed user
        assert callback_called is False
        # Should reply with authorization message
        mock_message.reply_text.assert_called_once_with("Not authorized.")

    @pytest.mark.asyncio
    async def test_handle_message_calls_on_message_callback(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify the callback receives (platform, user, text)."""
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)

        received_args: tuple[str, str, str] | None = None

        async def on_message(platform: str, user: str, text: str) -> None:
            nonlocal received_args
            received_args = (platform, user, text)

        adapter._on_message = on_message

        # Create mock update
        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.text = "Test message"
        mock_update.effective_message = mock_message

        await adapter._handle_message(mock_update, None)

        assert received_args is not None
        assert received_args[0] == "telegram"  # platform
        assert received_args[1] == "12345"     # user_id as string
        assert received_args[2] == "Test message"  # text

    @pytest.mark.asyncio
    async def test_start_initializes_application(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Verify polling starts and application initializes."""
        mock_app = AsyncMock(spec=Application)
        mock_updater = AsyncMock()
        mock_app.updater = mock_updater

        with patch(
            "hestia.platforms.telegram_adapter.Application.builder",
            return_value=MagicMock(
                token=MagicMock(return_value=MagicMock(
                    http_version=MagicMock(return_value=MagicMock(
                        build=MagicMock(return_value=mock_app)
                    ))
                ))
            ),
        ):
            callback_called = False

            async def on_message(platform: str, user: str, text: str) -> None:
                nonlocal callback_called
                callback_called = True

            # Start should initialize and begin polling
            await adapter.start(on_message)

            mock_app.initialize.assert_called_once()
            mock_app.start.assert_called_once()
            mock_updater.start_polling.assert_called_once()

            await adapter.stop()

    @pytest.mark.asyncio
    async def test_stop_shuts_down_cleanly(self, adapter: TelegramAdapter) -> None:
        """Verify cleanup happens properly on stop."""
        mock_app = AsyncMock(spec=Application)
        mock_updater = AsyncMock()
        mock_app.updater = mock_updater
        adapter._app = mock_app

        await adapter.stop()

        mock_updater.stop.assert_called_once()
        mock_app.stop.assert_called_once()
        mock_app.shutdown.assert_called_once()
        assert adapter._app is None

    @pytest.mark.asyncio
    async def test_send_error_sends_error_message(self, adapter: TelegramAdapter) -> None:
        """Verify send_error prepends error indicator."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        await adapter.send_error("12345", "Something went wrong")

        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="⚠️ Something went wrong",
            parse_mode="HTML",
        )

    @pytest.mark.asyncio
    async def test_send_system_warning_sends_warning_message(
        self, adapter: TelegramAdapter
    ) -> None:
        """Verify send_system_warning prepends warning indicator."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        await adapter.send_system_warning("12345", "Context budget exceeded")

        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="⚠️ Context budget exceeded",
            parse_mode="HTML",
        )

    @pytest.mark.asyncio
    async def test_send_message_raises_when_not_started(self, adapter: TelegramAdapter) -> None:
        """Verify proper error when trying to send before start."""
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.send_message("123", "test")

    @pytest.mark.asyncio
    async def test_edit_message_handles_unchanged_content(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Verify Telegram 'message not modified' error is handled gracefully."""
        from telegram.error import TelegramError

        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        # First edit succeeds
        await adapter.edit_message("12345", "100", "Test content")

        # Second edit with same content raises "message not modified"
        mock_bot.edit_message_text.side_effect = TelegramError(
            "Message is not modified"
        )

        # Should not raise - should log and continue
        await adapter.edit_message("12345", "100", "Test content")

        # Bot should have been called twice
        assert mock_bot.edit_message_text.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_start_sends_welcome(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /start command sends welcome message."""
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.reply_text = AsyncMock()
        mock_update.effective_message = mock_message

        await adapter._handle_start(mock_update, None)

        mock_message.reply_text.assert_called_once()
        call_args = mock_message.reply_text.call_args[0][0]
        assert "running" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_start_rejects_unauthorized(
        self,
        adapter: TelegramAdapter,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /start rejects unauthorized users."""
        telegram_config.allowed_users = ["allowed_user"]
        adapter = TelegramAdapter(telegram_config)

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "unauthorized_user"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.reply_text = AsyncMock()
        mock_update.effective_message = mock_message

        await adapter._handle_start(mock_update, None)

        mock_message.reply_text.assert_called_once_with("Not authorized.")
