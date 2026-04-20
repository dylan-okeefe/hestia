"""Unit tests for TelegramAdapter voice-message handler registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import Application, MessageHandler, filters

from hestia.config import TelegramConfig
from hestia.platforms.telegram_adapter import TelegramAdapter


@pytest.fixture
def telegram_config() -> TelegramConfig:
    return TelegramConfig(bot_token="test:token12345")


@pytest.fixture
def adapter(telegram_config: TelegramConfig) -> TelegramAdapter:
    return TelegramAdapter(telegram_config)


def _mock_builder_returns(mock_app: MagicMock) -> MagicMock:
    """Build the builder chain that returns ``mock_app``."""
    return MagicMock(
        token=MagicMock(
            return_value=MagicMock(
                http_version=MagicMock(
                    return_value=MagicMock(build=MagicMock(return_value=mock_app))
                )
            )
        )
    )


class TestVoiceHandlerRegistration:
    """Tests that the VOICE handler is registered conditionally."""

    @pytest.mark.asyncio
    async def test_voice_handler_registered_when_flag_true(self) -> None:
        """When voice_messages=True, a MessageHandler(filters.VOICE, ...) is added."""
        cfg = TelegramConfig(bot_token="test:token12345", voice_messages=True)
        adapter = TelegramAdapter(cfg)

        mock_app = MagicMock(spec=Application)
        mock_updater = AsyncMock()
        mock_app.updater = mock_updater

        with patch(
            "hestia.platforms.telegram_adapter.Application.builder",
            return_value=_mock_builder_returns(mock_app),
        ):
            await adapter.start(lambda p, u, t: None)

        # Find the VOICE handler among add_handler calls
        voice_handlers = [
            call_args[0][0]
            for call_args in mock_app.add_handler.call_args_list
            if isinstance(call_args[0][0], MessageHandler)
            and call_args[0][0].filters == filters.VOICE
        ]
        assert len(voice_handlers) == 1
        assert voice_handlers[0].callback == adapter._handle_voice_message

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_voice_handler_not_registered_when_flag_false(self) -> None:
        """When voice_messages=False, no MessageHandler(filters.VOICE, ...) is added."""
        cfg = TelegramConfig(bot_token="test:token12345", voice_messages=False)
        adapter = TelegramAdapter(cfg)

        mock_app = MagicMock(spec=Application)
        mock_updater = AsyncMock()
        mock_app.updater = mock_updater

        with patch(
            "hestia.platforms.telegram_adapter.Application.builder",
            return_value=_mock_builder_returns(mock_app),
        ):
            await adapter.start(lambda p, u, t: None)

        voice_handlers = [
            call_args[0][0]
            for call_args in mock_app.add_handler.call_args_list
            if isinstance(call_args[0][0], MessageHandler)
            and hasattr(call_args[0][0], "filters")
            and call_args[0][0].filters == filters.VOICE
        ]
        assert len(voice_handlers) == 0

        await adapter.stop()
