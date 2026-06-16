"""Tests for confirmation requester binding (L222 §4)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from nio import RoomSendResponse
from telegram import Bot, CallbackQuery, Message, Update
from telegram.ext import Application

from hestia.config import MatrixConfig, TelegramConfig
from hestia.platforms.confirmation import ConfirmationStore
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.platforms.telegram_adapter import TelegramAdapter


class TestConfirmationStoreBinding:
    """Tests for requester binding in the shared confirmation store."""

    @pytest.mark.asyncio
    async def test_approval_by_different_user_is_rejected(self):
        """A confirmation bound to one requester is denied when another approves."""
        store = ConfirmationStore()
        req = store.create(
            "terminal",
            {"command": "ls"},
            requester_platform_user="requester-1",
        )

        resolved = store.resolve(
            req.id, True, approver_platform_user="other-user"
        )

        assert resolved is True
        assert await req.future is False

    @pytest.mark.asyncio
    async def test_approval_by_requester_succeeds(self):
        """A confirmation bound to one requester succeeds when the same user approves."""
        store = ConfirmationStore()
        req = store.create(
            "terminal",
            {"command": "ls"},
            requester_platform_user="requester-1",
        )

        resolved = store.resolve(
            req.id, True, approver_platform_user="requester-1"
        )

        assert resolved is True
        assert await req.future is True

    @pytest.mark.asyncio
    async def test_denial_by_different_user_is_still_a_denial(self):
        """Even a 'no' from a different user is recorded as a denial (binding mismatch)."""
        store = ConfirmationStore()
        req = store.create(
            "terminal",
            {"command": "ls"},
            requester_platform_user="requester-1",
        )

        resolved = store.resolve(
            req.id, False, approver_platform_user="other-user"
        )

        assert resolved is True
        assert await req.future is False


class TestTelegramConfirmationBinding:
    """Tests for Telegram inline-keyboard confirmation binding."""

    @pytest.fixture
    def telegram_config(self) -> TelegramConfig:
        return TelegramConfig(bot_token="test:token12345")

    @pytest.fixture
    def adapter(self, telegram_config: TelegramConfig) -> TelegramAdapter:
        return TelegramAdapter(telegram_config)

    @pytest.mark.asyncio
    async def test_different_user_button_press_is_rejected(
        self, adapter: TelegramAdapter
    ) -> None:
        """A different group member pressing ✅ cannot approve the request."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 99
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "-1001234567890",
                "write_file",
                {"path": "test.txt"},
                requester_platform_user="12345",
            )
        )
        await asyncio.sleep(0.05)

        call_kwargs = mock_bot.send_message.call_args[1]
        keyboard = call_kwargs["reply_markup"].inline_keyboard
        yes_button = keyboard[0][0]

        mock_query = MagicMock(spec=CallbackQuery)
        mock_query.data = yes_button.callback_data
        mock_query.answer = AsyncMock()
        mock_query.message = None
        # A different user pressed the button
        mock_query.from_user = MagicMock()
        mock_query.from_user.id = 99999

        mock_update = MagicMock(spec=Update)
        mock_update.callback_query = mock_query

        await adapter._handle_callback_query(mock_update, None)

        result = await confirm_task
        assert result is False

    @pytest.mark.asyncio
    async def test_requester_button_press_is_accepted(
        self, adapter: TelegramAdapter
    ) -> None:
        """The original requester pressing ✅ approves the request."""
        mock_app = MagicMock(spec=Application)
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot

        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 99
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        adapter._app = mock_app

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "-1001234567890",
                "write_file",
                {"path": "test.txt"},
                requester_platform_user="12345",
            )
        )
        await asyncio.sleep(0.05)

        call_kwargs = mock_bot.send_message.call_args[1]
        keyboard = call_kwargs["reply_markup"].inline_keyboard
        yes_button = keyboard[0][0]

        mock_query = MagicMock(spec=CallbackQuery)
        mock_query.data = yes_button.callback_data
        mock_query.answer = AsyncMock()
        mock_query.message = None
        mock_query.from_user = MagicMock()
        mock_query.from_user.id = 12345

        mock_update = MagicMock(spec=Update)
        mock_update.callback_query = mock_query

        await adapter._handle_callback_query(mock_update, None)

        result = await confirm_task
        assert result is True


class TestMatrixConfirmationBinding:
    """Tests for Matrix reply-pattern confirmation binding."""

    @pytest.fixture
    def adapter(self) -> MatrixAdapter:
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        return MatrixAdapter(cfg)

    @pytest.mark.asyncio
    async def test_different_user_reply_is_rejected(self, adapter: MatrixAdapter) -> None:
        """A different room member replying 'yes' cannot approve the request."""
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(
            event_id="$event123", room_id="!room:matrix.org"
        )
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "!room:matrix.org",
                "write_file",
                {"path": "test.txt"},
                requester_platform_user="@requester:matrix.org",
            )
        )
        await asyncio.sleep(0.05)

        mock_event = MagicMock()
        mock_event.sender = "@other:matrix.org"
        mock_event.body = "yes"
        mock_event.source = {
            "content": {
                "m.relates_to": {
                    "m.in_reply_to": {"event_id": "$event123"}
                }
            }
        }

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        adapter._on_message = AsyncMock()
        await adapter._handle_room_message(mock_room, mock_event)

        result = await confirm_task
        assert result is False

    @pytest.mark.asyncio
    async def test_requester_reply_is_accepted(self, adapter: MatrixAdapter) -> None:
        """The original requester replying 'yes' approves the request."""
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(
            event_id="$event123", room_id="!room:matrix.org"
        )
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "!room:matrix.org",
                "write_file",
                {"path": "test.txt"},
                requester_platform_user="@requester:matrix.org",
            )
        )
        await asyncio.sleep(0.05)

        mock_event = MagicMock()
        mock_event.sender = "@requester:matrix.org"
        mock_event.body = "yes"
        mock_event.source = {
            "content": {
                "m.relates_to": {
                    "m.in_reply_to": {"event_id": "$event123"}
                }
            }
        }

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        adapter._on_message = AsyncMock()
        await adapter._handle_room_message(mock_room, mock_event)

        result = await confirm_task
        assert result is True
