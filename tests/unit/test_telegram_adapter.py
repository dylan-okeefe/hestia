"""Unit and async tests for TelegramAdapter.

These tests use pytest-asyncio to test actual async behavior with
mocked python-telegram-bot components.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot, Message, Update, User
from telegram.error import TelegramError
from telegram.ext import Application

from hestia.config import TelegramConfig
from hestia.platforms.telegram_adapter import TelegramAdapter, _split_long_text


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
    async def test_send_message_falls_back_to_plain_text_on_html_parse_error(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """If HTML parse fails, send_message retries the chunk as plain text."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 42
        mock_bot.send_message = AsyncMock(side_effect=[
            TelegramError("Can't parse entities: unsupported start tag \"code\" at byte offset 10"),
            mock_message,
        ])

        adapter._app = mock_app

        result = await adapter.send_message("12345", "some text")

        assert mock_bot.send_message.call_count == 2
        second_call = mock_bot.send_message.call_args
        assert second_call.kwargs["parse_mode"] is None
        assert second_call.kwargs["text"] == "some text"
        assert result == "42"

    @pytest.mark.asyncio
    async def test_send_long_fenced_code_block_splits_and_sends(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """A fenced code block longer than the chunk limit is split and sent."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 1
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app

        # Build a fenced code block that exceeds the safe chunk length.
        line = "x" * 100
        block = "```\n" + "\n".join([line] * 50) + "\n```"
        assert len(block) > 3800

        result = await adapter.send_message("12345", block)

        assert result == "1"
        assert mock_bot.send_message.call_count > 1
        # Every call should attempt HTML first; plain-text fallback is exercised
        # only on parse errors.
        for call in mock_bot.send_message.call_args_list:
            assert call.kwargs.get("parse_mode") == "HTML"

    @pytest.mark.asyncio
    async def test_edit_message_falls_back_to_plain_text_on_html_parse_error(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """If HTML parse fails during edit, retry the edit as plain text."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_bot.edit_message_text = AsyncMock(side_effect=[
            TelegramError("Can't parse entities: invalid entity at byte offset 5"),
            None,
        ])

        adapter._app = mock_app

        await adapter.edit_message("12345", "100", "some text")

        assert mock_bot.edit_message_text.call_count == 2
        second_call = mock_bot.edit_message_text.call_args
        assert second_call.kwargs["parse_mode"] is None
        assert second_call.kwargs["text"] == "some text"

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

        async def on_message(
            platform: str,
            user: str,
            text: str,
            sender: str | None,
            session_title: str | None = None,
        ) -> None:
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

        received_args: tuple[str, str, str, str | None, str | None, list[str] | None] | None = None

        async def on_message(
            platform: str,
            user: str,
            text: str,
            sender: str | None,
            session_title: str | None = None,
            images: list[str] | None = None,
        ) -> None:
            nonlocal received_args
            received_args = (platform, user, text, sender, session_title, images)

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
        assert received_args[3] is None  # sender_platform_user in private chat
        assert received_args[4] is None  # session_title in private chat
        assert received_args[5] is None  # images: text messages carry no attachments

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

            async def on_message(
            platform: str,
            user: str,
            text: str,
            sender: str | None,
            session_title: str | None = None,
        ) -> None:
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


class TestTelegramAdapterReset:
    """Tests for the /reset command."""

    @pytest.mark.asyncio
    async def test_handle_reset_archives_active_session_and_clears_cache(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /reset archives the active session and invokes the cache callback."""
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)

        mock_session = MagicMock()
        mock_session.id = "telegram_12345_test"
        mock_session.platform_user = "12345"

        mock_session_store = AsyncMock()
        mock_session_store.get_active_session = AsyncMock(return_value=mock_session)
        adapter._session_store = mock_session_store

        mock_handoff_service = AsyncMock()
        adapter._handoff_service = mock_handoff_service

        cache_cleared = False

        async def reset_callback(platform_user: str) -> None:
            nonlocal cache_cleared
            cache_cleared = True
            assert platform_user == "12345"

        adapter.register_reset_callback(reset_callback)

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.reply_text = AsyncMock()
        mock_update.effective_message = mock_message

        await adapter._handle_reset(mock_update, None)

        mock_session_store.get_active_session.assert_called_once_with("telegram", "12345")
        mock_handoff_service.generate_handoff_summary.assert_awaited_once_with(
            "telegram_12345_test"
        )
        assert cache_cleared is True
        mock_message.reply_text.assert_called_once()
        assert "reset" in mock_message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_reset_no_active_session(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /reset replies gracefully when there is no active session."""
        telegram_config.allowed_users = ["12345"]
        adapter = TelegramAdapter(telegram_config)

        mock_session_store = AsyncMock()
        mock_session_store.get_active_session = AsyncMock(return_value=None)
        adapter._session_store = mock_session_store

        mock_handoff_service = AsyncMock()
        adapter._handoff_service = mock_handoff_service

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.reply_text = AsyncMock()
        mock_update.effective_message = mock_message

        await adapter._handle_reset(mock_update, None)

        mock_handoff_service.generate_handoff_summary.assert_not_called()
        mock_message.reply_text.assert_called_once()
        assert "no active" in mock_message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_reset_rejects_unauthorized(
        self,
        adapter: TelegramAdapter,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /reset rejects unauthorized users."""
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

        await adapter._handle_reset(mock_update, None)

        mock_message.reply_text.assert_called_once_with("Not authorized.")


class TestTelegramAdapterCommands:
    """Tests for the /commands and /help command handlers."""

    @pytest.mark.asyncio
    async def test_handle_commands_renders_registry_catalog(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /commands replies with the registry catalog."""
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

        await adapter._handle_commands(mock_update, None)

        mock_message.reply_text.assert_called_once()
        text = mock_message.reply_text.call_args[0][0]
        assert "Available commands:" in text
        assert "/commands" in text
        assert "/help" in text

    @pytest.mark.asyncio
    async def test_handle_help_aliases_commands(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /help replies with the same catalog as /commands."""
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

        await adapter._handle_help(mock_update, None)

        mock_message.reply_text.assert_called_once()
        text = mock_message.reply_text.call_args[0][0]
        assert "Available commands:" in text

    @pytest.mark.asyncio
    async def test_handle_commands_rejects_unauthorized(
        self,
        telegram_config: TelegramConfig,
    ) -> None:
        """Verify /commands rejects unauthorized users."""
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

        await adapter._handle_commands(mock_update, None)

        mock_message.reply_text.assert_called_once_with("Not authorized.")


class TestTelegramAdapterStreaming:
    """Tests for TelegramAdapter progressive streaming delivery."""

    @pytest.mark.asyncio
    async def test_stream_callback_sends_first_message_at_20_chars(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """First chunk is buffered until at least 20 chars accumulated."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        callback = adapter._make_stream_callback("12345")

        await callback("Hello")
        mock_bot.send_message.assert_not_called()

        await callback(" world! This is long enough.")
        mock_bot.send_message.assert_called_once_with(
            chat_id=12345,
            text="Hello world! This is long enough.",
            parse_mode="HTML",
        )

    @pytest.mark.asyncio
    async def test_stream_callback_sends_first_message_after_500ms(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """First chunk is buffered until 500 ms have elapsed."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        callback = adapter._make_stream_callback("12345")

        await callback("Hi")
        mock_bot.send_message.assert_not_called()

        await asyncio.sleep(0.6)
        await callback("!")
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_callback_rate_limits_edits(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Subsequent edits are rate-limited to 1.5 s."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 42
        mock_bot.send_message = AsyncMock(return_value=mock_message)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        callback = adapter._make_stream_callback("12345")

        # First message triggers immediately (>= 20 chars)
        await callback("This is a long first message!!")
        assert mock_bot.send_message.call_count == 1

        # Immediate edit should be skipped
        await callback(" more")
        mock_bot.edit_message_text.assert_not_called()

        # After 1.5 s, edit should go through
        await asyncio.sleep(1.5)
        await callback(" text")
        mock_bot.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_callback_uses_edit_for_subsequent_chunks(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """After first message, subsequent chunks trigger edit_message."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 42
        mock_bot.send_message = AsyncMock(return_value=mock_message)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        callback = adapter._make_stream_callback("12345")

        await callback("First message is long enough.")
        assert mock_bot.send_message.call_count == 1

        await asyncio.sleep(1.5)
        await callback(" Added text.")
        mock_bot.edit_message_text.assert_called_once_with(
            chat_id=12345,
            message_id=42,
            text="First message is long enough. Added text.",
            parse_mode="HTML",
        )


class TestTelegramAdapterLongMessages:
    """Tests for splitting messages that exceed Telegram's length limit."""

    def test_split_long_text_short_text_unchanged(self) -> None:
        """Text under the limit is not split."""
        text = "Short message"
        assert _split_long_text(text) == [text]

    def test_split_long_text_prefers_paragraph_boundary(self) -> None:
        """Splitting prefers paragraph boundaries."""
        paragraph = "word " * 700  # ~3500 chars
        text = paragraph + "\n\n" + paragraph
        chunks = _split_long_text(text)
        assert len(chunks) == 2
        assert all(len(chunk) <= 3800 for chunk in chunks)

    def test_split_long_text_falls_back_to_sentence(self) -> None:
        """When no paragraph/line boundary exists, split at sentence end."""
        text = "Hello world. " * 400  # ~5200 chars, no newlines
        chunks = _split_long_text(text)
        assert len(chunks) >= 2
        assert all(len(chunk) <= 3800 for chunk in chunks)

    def test_split_long_text_falls_back_to_word(self) -> None:
        """When no sentence boundary exists, split at word boundary."""
        text = "a " * 3000  # ~6000 chars
        chunks = _split_long_text(text)
        assert len(chunks) >= 2
        assert all(len(chunk) <= 3800 for chunk in chunks)

    @pytest.mark.asyncio
    async def test_send_message_splits_long_text(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Long messages are sent as multiple Telegram messages."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_messages = [
            MagicMock(spec=Message, message_id=1),
            MagicMock(spec=Message, message_id=2),
        ]
        mock_bot.send_message = AsyncMock(side_effect=mock_messages)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        long_text = "word " * 1000  # ~5000 chars
        result = await adapter.send_message("12345", long_text)

        assert mock_bot.send_message.call_count == 2
        assert result == "1"

    @pytest.mark.asyncio
    async def test_edit_message_splits_long_text(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """Editing with long text replaces original and sends follow-ups."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        adapter._app = mock_app

        long_text = "word " * 1000  # ~5000 chars
        await adapter.edit_message("12345", "100", long_text)

        assert mock_bot.edit_message_text.call_count == 1
        assert mock_bot.send_message.call_count == 1


class TestTelegramAdapterPhotos:
    """L234 vision: photo handler download/gating/caption behavior.

    The ffmpeg transform itself is covered by integration tests with a real
    ffmpeg binary; here ``_photo_to_jpeg_data_url`` is stubbed and we assert
    the call shape plus the handler's routing decisions.
    """

    @pytest.fixture
    def vision_config(self) -> TelegramConfig:
        return TelegramConfig(
            bot_token="test:token12345",
            vision=True,
            allowed_users=["12345"],
        )

    @pytest.fixture
    def vision_adapter(self, vision_config: TelegramConfig) -> TelegramAdapter:
        return TelegramAdapter(vision_config)

    def _make_photo_update(
        self,
        caption: str | None = None,
        file_size: int | None = 50_000,
        download_error: Exception | None = None,
    ) -> MagicMock:
        """Build a mock Update carrying a photo message like Telegram sends."""
        from telegram import PhotoSize

        mock_update = MagicMock(spec=Update)
        mock_user = MagicMock(spec=User)
        mock_user.id = 12345
        mock_user.username = "testuser"
        mock_update.effective_user = mock_user

        mock_message = MagicMock(spec=Message)
        mock_message.caption = caption

        mock_file = AsyncMock()

        def _download(path: str, **kwargs: object) -> None:
            if download_error is not None:
                raise download_error
            with open(path, "wb") as fh:
                fh.write(b"\xff\xd8\xff\xe0fake-jpeg-payload")

        mock_file.download_to_drive = AsyncMock(side_effect=_download)

        small = MagicMock(spec=PhotoSize)
        small.file_size = 1_000
        large = MagicMock(spec=PhotoSize)
        large.file_size = file_size
        large.get_file = AsyncMock(return_value=mock_file)
        mock_message.photo = [small, large]
        mock_message.reply_text = AsyncMock()

        mock_update.effective_message = mock_message
        return mock_update

    @pytest.mark.asyncio
    async def test_photo_disabled_vision_replies_once_and_drops(
        self,
        vision_config: TelegramConfig,
    ) -> None:
        """vision=False: reply with a note, do not download or route (L234 §2.4)."""
        vision_config.vision = False
        adapter = TelegramAdapter(vision_config)
        update = self._make_photo_update(caption="hi")
        callback_called = False

        async def on_message(*args: object, **kwargs: object) -> None:
            nonlocal callback_called
            callback_called = True

        adapter._on_message = on_message

        await adapter._handle_photo(update, None)

        message = update.effective_message
        message.reply_text.assert_called_once()
        note = message.reply_text.call_args.args[0]
        assert "can't see images" in note
        assert message.photo[-1].get_file.await_count == 0
        assert callback_called is False

    @pytest.mark.asyncio
    async def test_photo_enabled_downloads_largest_and_routes_with_caption(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """vision=True: download largest PhotoSize, caption becomes text, images ride along."""
        update = self._make_photo_update(caption="what is this?")
        received: dict[str, object] = {}

        async def on_message(
            platform: str,
            user: str,
            text: str,
            sender: str | None,
            session_title: str | None = None,
            images: list[str] | None = None,
        ) -> None:
            received.update(
                platform=platform, user=user, text=text,
                sender=sender, session_title=session_title, images=images,
            )

        vision_adapter._on_message = on_message

        data_url = "data:image/jpeg;base64,QUJDRA=="
        with patch.object(
            vision_adapter, "_photo_to_jpeg_data_url", new=AsyncMock(return_value=data_url)
        ) as mock_convert:
            await vision_adapter._handle_photo(update, None)

        assert received["platform"] == "telegram"
        assert received["user"] == "12345"
        assert received["text"] == "what is this?"  # caption passthrough
        assert received["sender"] is None  # private chat
        assert received["images"] == [data_url]

        # Largest PhotoSize was used, transform called with the configured edge cap
        assert update.effective_message.photo[-1].get_file.await_count == 1
        mock_convert.assert_awaited_once()
        assert mock_convert.await_args.args[0].endswith(".jpg")
        assert mock_convert.await_args.kwargs["max_edge"] == 1024

    @pytest.mark.asyncio
    async def test_photo_enabled_empty_caption_defaults_to_empty_text(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """A photo without a caption routes with an empty message text."""
        update = self._make_photo_update(caption=None)
        received: dict[str, object] = {}

        async def on_message(
            platform: str,
            user: str,
            text: str,
            sender: str | None,
            session_title: str | None = None,
            images: list[str] | None = None,
        ) -> None:
            received.update(text=text, images=images)

        vision_adapter._on_message = on_message

        with patch.object(
            vision_adapter, "_photo_to_jpeg_data_url", new=AsyncMock(return_value="data:image/jpeg;base64,QQ==")
        ):
            await vision_adapter._handle_photo(update, None)

        assert received["text"] == ""
        assert received["images"] == ["data:image/jpeg;base64,QQ=="]

    @pytest.mark.asyncio
    async def test_photo_download_failure_replies_and_stops(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """A failed Telegram download replies with an apology and never routes."""
        from telegram.error import TelegramError

        update = self._make_photo_update(download_error=TelegramError("network down"))
        callback_called = False

        async def on_message(*args: object, **kwargs: object) -> None:
            nonlocal callback_called
            callback_called = True

        vision_adapter._on_message = on_message

        await vision_adapter._handle_photo(update, None)

        message = update.effective_message
        message.reply_text.assert_called_once()
        assert "download" in message.reply_text.call_args.args[0].lower()
        assert callback_called is False

    @pytest.mark.asyncio
    async def test_photo_oversize_declared_file_rejected_before_download(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """A PhotoSize declaring >10MB is rejected before any download."""
        update = self._make_photo_update(file_size=11 * 1024 * 1024)
        callback_called = False

        async def on_message(*args: object, **kwargs: object) -> None:
            nonlocal callback_called
            callback_called = True

        vision_adapter._on_message = on_message

        await vision_adapter._handle_photo(update, None)

        message = update.effective_message
        message.reply_text.assert_called_once()
        assert "too large" in message.reply_text.call_args.args[0].lower()
        assert message.photo[-1].get_file.await_count == 0
        assert callback_called is False

    @pytest.mark.asyncio
    async def test_photo_conversion_failure_replies_and_stops(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """A failed ffmpeg conversion replies with an apology and never routes."""
        update = self._make_photo_update()
        callback_called = False

        async def on_message(*args: object, **kwargs: object) -> None:
            nonlocal callback_called
            callback_called = True

        vision_adapter._on_message = on_message

        with patch.object(
            vision_adapter,
            "_photo_to_jpeg_data_url",
            new=AsyncMock(side_effect=RuntimeError("ffmpeg photo→jpeg failed: boom")),
        ):
            await vision_adapter._handle_photo(update, None)

        message = update.effective_message
        message.reply_text.assert_called_once()
        assert "process" in message.reply_text.call_args.args[0].lower()
        assert callback_called is False

    @pytest.mark.asyncio
    async def test_photo_rejected_for_disallowed_user(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """Unauthorized senders get the standard Not authorized. reply."""
        update = self._make_photo_update()
        update.effective_user.id = 99999

        await vision_adapter._handle_photo(update, None)

        update.effective_message.reply_text.assert_called_once_with("Not authorized.")
        assert update.effective_message.photo[-1].get_file.await_count == 0

    @pytest.mark.asyncio
    async def test_start_registers_photo_handler(
        self,
        adapter: TelegramAdapter,
    ) -> None:
        """start() registers the PHOTO handler next to the text handler (L234 §2.1)."""
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
            await adapter.start(AsyncMock())

        registered = [call.args[0] for call in mock_app.add_handler.call_args_list]
        photo_handlers = [
            h for h in registered
            if getattr(h, "callback", None) == adapter._handle_photo
        ]
        assert len(photo_handlers) == 1
        assert "PHOTO" in photo_handlers[0].filters.name

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_jpeg_retry_steps_on_oversize_output(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """Output over the 400KB cap retries at lower quality, then smaller edge."""
        calls: list[tuple[int, int]] = []

        async def fake_ffmpeg(src: str, max_edge: int, quality: int) -> bytes:
            calls.append((max_edge, quality))
            if len(calls) == 1:
                return b"x" * 500_000  # over cap → retry
            if len(calls) == 2:
                return b"x" * 450_000  # still over → smaller edge
            return b"x" * 300_000  # fits

        with patch.object(
            vision_adapter, "_ffmpeg_jpeg", new=AsyncMock(side_effect=fake_ffmpeg)
        ):
            url = await vision_adapter._photo_to_jpeg_data_url("/tmp/x.jpg", max_edge=1024)

        assert calls == [(1024, 4), (1024, 8), (614, 8)]
        expected = "data:image/jpeg;base64," + base64.b64encode(b"x" * 300_000).decode("ascii")
        assert url == expected

    @pytest.mark.asyncio
    async def test_jpeg_raises_when_cap_unreachable(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """If every retry stays over the cap the transform raises (handler replies)."""
        with patch.object(
            vision_adapter, "_ffmpeg_jpeg", new=AsyncMock(return_value=b"x" * 500_000)
        ), pytest.raises(RuntimeError, match="exceeds"):
            await vision_adapter._photo_to_jpeg_data_url("/tmp/x.jpg", max_edge=1024)

    @pytest.mark.asyncio
    async def test_ffmpeg_jpeg_invocation_shape(
        self,
        vision_adapter: TelegramAdapter,
    ) -> None:
        """_ffmpeg_jpeg shells out to ffmpeg with scale/JPEG args (mirrors _ogg_to_pcm)."""
        captured: dict[str, object] = {}

        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"\xff\xd8jpeg", b""))
        proc.returncode = 0

        async def fake_exec(*args: str, **kwargs: object) -> AsyncMock:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return proc

        with patch(
            "hestia.platforms.telegram_adapter.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=fake_exec),
        ):
            out = await vision_adapter._ffmpeg_jpeg("/tmp/in.jpg", max_edge=1024, quality=4)

        assert out == b"\xff\xd8jpeg"
        args = captured["args"]
        assert args[0] == "ffmpeg"
        assert "-i" in args and "/tmp/in.jpg" in args
        vf = args[args.index("-vf") + 1]
        assert "scale='min(1024,iw)'" in vf
        assert "force_original_aspect_ratio=decrease" in vf
        assert args[args.index("-q:v") + 1] == "4"
        assert args[args.index("-f") + 1] == "mjpeg"
        assert captured["kwargs"]["stdout"] is asyncio.subprocess.PIPE
