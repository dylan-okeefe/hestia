"""Unit tests for TelegramAdapter confirmation flow."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Bot, CallbackQuery, Message, Update
from telegram.ext import Application

from hestia.config import TelegramConfig
from hestia.platforms.telegram_adapter import TelegramAdapter


@pytest.fixture
def telegram_config() -> TelegramConfig:
    return TelegramConfig(bot_token="test:token12345")


@pytest.fixture
def adapter(telegram_config: TelegramConfig) -> TelegramAdapter:
    return TelegramAdapter(telegram_config)


class TestTelegramConfirmation:
    """Tests for the inline-keyboard confirmation flow."""

    @pytest.mark.asyncio
    async def test_request_confirmation_sends_inline_keyboard(self, adapter):
        """Verify the confirmation message includes ✅/❌ buttons."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 99
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app

        # Trigger confirmation in background so we can simulate the callback
        confirm_task = asyncio.create_task(
            adapter.request_confirmation("12345", "write_file", {"path": "test.txt"})
        )

        # Give the task a moment to send the message and create the request
        await asyncio.sleep(0.05)

        assert mock_bot.send_message.call_count == 1
        call_kwargs = mock_bot.send_message.call_args[1]
        assert "write_file" in call_kwargs["text"]
        assert call_kwargs["reply_markup"] is not None

        # Extract the callback_data from the keyboard
        keyboard = call_kwargs["reply_markup"].inline_keyboard
        yes_button = keyboard[0][0]
        assert yes_button.text == "✅"
        assert yes_button.callback_data.startswith("confirm:")

        # Simulate pressing ✅
        callback_data = yes_button.callback_data
        callback_data.split(":")[1]

        mock_query = MagicMock(spec=CallbackQuery)
        mock_query.data = callback_data
        mock_query.answer = AsyncMock()
        mock_query.message = None

        mock_update = MagicMock(spec=Update)
        mock_update.callback_query = mock_query

        await adapter._handle_callback_query(mock_update, None)

        result = await confirm_task
        assert result is True

    @pytest.mark.asyncio
    async def test_request_confirmation_denied(self, adapter):
        """Verify ❌ returns False."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 99
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app

        confirm_task = asyncio.create_task(
            adapter.request_confirmation("12345", "terminal", {"command": "ls"})
        )
        await asyncio.sleep(0.05)

        call_kwargs = mock_bot.send_message.call_args[1]
        keyboard = call_kwargs["reply_markup"].inline_keyboard
        no_button = keyboard[0][1]
        assert no_button.text == "❌"

        mock_query = MagicMock(spec=CallbackQuery)
        mock_query.data = no_button.callback_data
        mock_query.answer = AsyncMock()
        mock_query.message = None

        mock_update = MagicMock(spec=Update)
        mock_update.callback_query = mock_query

        await adapter._handle_callback_query(mock_update, None)

        result = await confirm_task
        assert result is False

    @pytest.mark.asyncio
    async def test_request_confirmation_times_out(self, adapter):
        """Verify timeout returns False."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 99
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app
        adapter._confirmation_timeout_seconds = 0.05

        result = await adapter.request_confirmation(
            "12345", "write_file", {"path": "test.txt"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_callback_query_ignores_expired(self, adapter):
        """Verify answering an expired confirmation is handled gracefully."""
        mock_query = MagicMock(spec=CallbackQuery)
        mock_query.data = "confirm:expired-id:yes"
        mock_query.answer = AsyncMock()

        mock_update = MagicMock(spec=Update)
        mock_update.callback_query = mock_query

        await adapter._handle_callback_query(mock_update, None)

        mock_query.answer.assert_called_once_with("This confirmation has expired.")

    @pytest.mark.asyncio
    async def test_handle_callback_query_ignores_non_confirm(self, adapter):
        """Verify non-confirm callback_data is ignored."""
        mock_query = MagicMock(spec=CallbackQuery)
        mock_query.data = "some_other_data"
        mock_query.answer = AsyncMock()

        mock_update = MagicMock(spec=Update)
        mock_update.callback_query = mock_query

        await adapter._handle_callback_query(mock_update, None)

        mock_query.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_confirmation_raises_when_not_started(self, adapter):
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.request_confirmation("123", "terminal", {})
