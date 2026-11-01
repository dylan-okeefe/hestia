"""Login-code messages self-delete after LOGIN_CODE_TTL_S seconds.

TaskView #84: dashboard login codes sent over Telegram must not persist in
the chat history. ``AuthManager.request_code`` schedules a best-effort
deletion of the sent code message after the TTL.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Bot, Message
from telegram.error import BadRequest
from telegram.ext import Application

from hestia.config import TelegramConfig, WebConfig
from hestia.platforms.base import IncomingMessageCallback, Platform
from hestia.platforms.telegram_adapter import TelegramAdapter
from hestia.web import auth as auth_module
from hestia.web.auth import LOGIN_CODE_TTL_S, AuthManager


@pytest.fixture
def telegram_config() -> TelegramConfig:
    return TelegramConfig(bot_token="test:token12345", allowed_users=["12345"])


@pytest.fixture
def tg_adapter(telegram_config: TelegramConfig) -> TelegramAdapter:
    return TelegramAdapter(telegram_config)


def _mock_app_with_bot() -> tuple[MagicMock, AsyncMock]:
    mock_app = MagicMock(spec=Application)
    mock_bot = AsyncMock(spec=Bot)
    mock_app.bot = mock_bot
    return mock_app, mock_bot


class TestTelegramSendReturnsMessageId:
    """Requirement 1: send_message returns the platform message id."""

    async def test_send_message_returns_message_id(self, tg_adapter: TelegramAdapter) -> None:
        mock_app, mock_bot = _mock_app_with_bot()
        mock_message = MagicMock(spec=Message)
        mock_message.message_id = 42
        mock_bot.send_message = AsyncMock(return_value=mock_message)
        tg_adapter._app = mock_app

        result = await tg_adapter.send_message("12345", "Your Hestia dashboard code is: 123456")

        assert result == "42"


class TestTelegramDeleteMessage:
    """Requirement 2: delete_message deletes via the PTB bot, BadRequest-safe."""

    async def test_delete_message_calls_bot(self, tg_adapter: TelegramAdapter) -> None:
        mock_app, mock_bot = _mock_app_with_bot()
        tg_adapter._app = mock_app

        await tg_adapter.delete_message("12345", "42")

        mock_bot.delete_message.assert_awaited_once_with(chat_id=12345, message_id=42)

    async def test_delete_message_swallows_bad_request(
        self, tg_adapter: TelegramAdapter, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_app, mock_bot = _mock_app_with_bot()
        mock_bot.delete_message = AsyncMock(side_effect=BadRequest("Message to delete not found"))
        tg_adapter._app = mock_app

        with caplog.at_level(logging.DEBUG, logger="hestia.platforms.telegram_adapter"):
            await tg_adapter.delete_message("12345", "42")  # must not raise

        mock_bot.delete_message.assert_awaited_once()

    async def test_delete_message_noop_when_not_started(self, tg_adapter: TelegramAdapter) -> None:
        await tg_adapter.delete_message("12345", "42")  # no app attached; must not raise


class FakeTelegramPlatform(Platform):
    """Minimal telegram-like platform supporting deletion."""

    def __init__(self, msg_id: str | None = "42", fail_delete: bool = False) -> None:
        self._config = MagicMock(allowed_users=["12345"])
        self.sent: list[tuple[str, str]] = []
        self.deleted: list[tuple[str, str]] = []
        self._msg_id = msg_id
        self._fail_delete = fail_delete

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self, on_message: IncomingMessageCallback) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_message(self, user: str, text: str) -> str | None:
        self.sent.append((user, text))
        return self._msg_id

    async def edit_message(self, user: str, msg_id: str, text: str, **kwargs: Any) -> None:
        return None

    async def send_error(self, user: str, text: str) -> None:
        return None

    async def delete_message(self, user: str, msg_id: str) -> None:
        if self._fail_delete:
            raise RuntimeError("telegram exploded")
        self.deleted.append((user, msg_id))


@pytest.fixture
def web_config() -> WebConfig:
    return WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )


class TestLoginCodeSelfDestruction:
    """Requirement 3: the auth flow schedules deletion of the code message."""

    async def test_deletion_task_fires_after_ttl(
        self,
        web_config: WebConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        platform = FakeTelegramPlatform(msg_id="42")
        manager = AuthManager(adapters={"telegram": platform}, config=web_config)
        monkeypatch.setattr(auth_module, "LOGIN_CODE_TTL_S", 0)

        result = await manager.request_code("telegram")

        assert result["status"] == "sent"
        await asyncio.sleep(0)  # let the timer task run
        await asyncio.gather(*manager._deletion_tasks, return_exceptions=True)

        assert platform.deleted == [("12345", "42")]

    async def test_default_ttl_is_five_minutes(self) -> None:
        assert LOGIN_CODE_TTL_S == 300

    async def test_deletion_failure_is_logged_not_raised(
        self,
        web_config: WebConfig,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        platform = FakeTelegramPlatform(msg_id="42", fail_delete=True)
        manager = AuthManager(adapters={"telegram": platform}, config=web_config)
        monkeypatch.setattr(auth_module, "LOGIN_CODE_TTL_S", 0)

        with caplog.at_level(logging.WARNING, logger="hestia.web.auth"):
            result = await manager.request_code("telegram")  # must not raise
            await asyncio.sleep(0)
            await asyncio.gather(*manager._deletion_tasks, return_exceptions=True)

        assert result["status"] == "sent"
        assert any("Failed to self-delete login code message" in r.message for r in caplog.records)

    async def test_no_message_id_skips_scheduling(
        self,
        web_config: WebConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        platform = FakeTelegramPlatform(msg_id=None)
        manager = AuthManager(adapters={"telegram": platform}, config=web_config)
        monkeypatch.setattr(auth_module, "LOGIN_CODE_TTL_S", 0)

        result = await manager.request_code("telegram")
        await asyncio.sleep(0)

        assert result["status"] == "sent"
        assert platform.deleted == []
        assert manager._deletion_tasks == set()

    async def test_platform_without_delete_support_skips_scheduling(
        self,
        web_config: WebConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A platform using the base-class no-op delete is left alone."""

        class NoDeletePlatform(FakeTelegramPlatform):
            delete_message = Platform.delete_message  # type: ignore[assignment]

        platform = NoDeletePlatform(msg_id="42")
        manager = AuthManager(adapters={"telegram": platform}, config=web_config)
        monkeypatch.setattr(auth_module, "LOGIN_CODE_TTL_S", 0)

        result = await manager.request_code("telegram")
        await asyncio.sleep(0)

        assert result["status"] == "sent"
        assert manager._deletion_tasks == set()

    async def test_non_telegram_platform_with_delete_also_schedules(
        self,
        web_config: WebConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Matrix-style platforms (event id + redact) work the same way."""

        class MatrixLikePlatform(FakeTelegramPlatform):
            @property
            def name(self) -> str:
                return "matrix"

        platform = MatrixLikePlatform(msg_id="$event_1")
        platform._config = MagicMock(
            allowed_users=["!room:matrix.org"],
            allowed_rooms=["!room:matrix.org"],
        )
        manager = AuthManager(
            adapters={"matrix": platform},
            config=web_config,
        )
        monkeypatch.setattr(auth_module, "LOGIN_CODE_TTL_S", 0)

        await manager.request_code("matrix")
        await asyncio.sleep(0)
        await asyncio.gather(*manager._deletion_tasks, return_exceptions=True)

        assert platform.deleted == [("!room:matrix.org", "$event_1")]
