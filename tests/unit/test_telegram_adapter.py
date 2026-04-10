"""Unit tests for TelegramAdapter."""

import pytest

from hestia.config import TelegramConfig
from hestia.platforms.telegram_adapter import TelegramAdapter


class TestTelegramAdapter:
    def test_name_is_telegram(self):
        cfg = TelegramConfig(bot_token="test:token")
        adapter = TelegramAdapter(cfg)
        assert adapter.name == "telegram"

    def test_requires_bot_token(self):
        cfg = TelegramConfig(bot_token="")
        with pytest.raises(ValueError, match="bot_token is required"):
            TelegramAdapter(cfg)

    def test_allowed_users_empty_allows_all(self):
        cfg = TelegramConfig(bot_token="test:token")
        adapter = TelegramAdapter(cfg)
        assert adapter._is_allowed(12345, "testuser") is True

    def test_allowed_users_by_id(self):
        cfg = TelegramConfig(bot_token="test:token", allowed_users=["12345"])
        adapter = TelegramAdapter(cfg)
        assert adapter._is_allowed(12345, "testuser") is True
        assert adapter._is_allowed(99999, "other") is False

    def test_allowed_users_by_username(self):
        cfg = TelegramConfig(bot_token="test:token", allowed_users=["dylan"])
        adapter = TelegramAdapter(cfg)
        assert adapter._is_allowed(12345, "dylan") is True
        assert adapter._is_allowed(12345, "other") is False

    def test_send_message_raises_when_not_started(self):
        cfg = TelegramConfig(bot_token="test:token")
        adapter = TelegramAdapter(cfg)
        with pytest.raises(RuntimeError, match="not started"):
            import asyncio
            asyncio.run(adapter.send_message("123", "test"))
