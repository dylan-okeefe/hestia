"""Tests for PlatformNotifier."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hestia.platforms.notifier import PlatformNotifier


@pytest.fixture
def notifier() -> PlatformNotifier:
    config = MagicMock()
    config.telegram = MagicMock(bot_token="test_token")
    config.matrix = MagicMock(homeserver="", user_id="", access_token="")
    return PlatformNotifier(config)


class TestTelegramBotCache:
    """Tests for Telegram Bot instance caching."""

    def test_bot_instance_reused(self, notifier: PlatformNotifier) -> None:
        """The same Bot instance is returned on multiple calls."""
        with patch("telegram.Bot") as mock_bot_cls:
            mock_instance = MagicMock()
            mock_bot_cls.return_value = mock_instance

            bot1 = notifier._get_telegram_bot()
            bot2 = notifier._get_telegram_bot()

            assert bot1 is bot2
            mock_bot_cls.assert_called_once_with(token="test_token")

    @pytest.mark.asyncio
    async def test_close_shutdowns_bot(self, notifier: PlatformNotifier) -> None:
        """close() calls shutdown on the cached bot and clears it."""
        with patch("telegram.Bot") as mock_bot_cls:
            from unittest.mock import AsyncMock

            mock_instance = MagicMock()
            mock_instance.shutdown = AsyncMock(return_value=None)
            mock_bot_cls.return_value = mock_instance

            notifier._get_telegram_bot()
            await notifier.close()

            mock_instance.shutdown.assert_awaited_once()
            assert notifier._telegram_bot is None


class TestMatrixTxnId:
    """Tests for Matrix transaction ID generation."""

    @pytest.mark.asyncio
    async def test_txn_id_is_unique(self, notifier: PlatformNotifier) -> None:
        """Each Matrix send uses a unique txn_id."""
        from unittest.mock import AsyncMock

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            notifier._config.matrix = MagicMock(
                homeserver="https://matrix.example.com",
                access_token="token123",
            )

            await notifier._send_matrix("!room:matrix.org", "hello")
            await notifier._send_matrix("!room:matrix.org", "hello")

            calls = mock_client.put.await_args_list
            assert len(calls) == 2
            url1 = calls[0][0][0]
            url2 = calls[1][0][0]
            assert url1 != url2
