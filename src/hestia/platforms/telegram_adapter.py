"""Telegram platform adapter."""

from __future__ import annotations

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from hestia.config import TelegramConfig
from hestia.platforms.base import IncomingMessageCallback, Platform

logger = logging.getLogger(__name__)


class TelegramAdapter(Platform):
    """Telegram platform adapter using python-telegram-bot.

    Design decisions from Hermes experience:
    - Force HTTP/1.1 via httpx (HTTP/2 causes intermittent Telegram API failures)
    - Rate-limit edit_message to avoid Telegram 429 (max 1 edit per 1.5s per message)
    - Allowed-users whitelist for single-user security
    """

    def __init__(self, config: TelegramConfig) -> None:
        if not config.bot_token:
            raise ValueError("Telegram bot_token is required")

        self._config = config
        self._app: Application | None = None
        self._on_message: IncomingMessageCallback | None = None
        self._last_edit_times: dict[str, float] = {}  # msg_id -> last edit timestamp

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Start polling for Telegram messages."""
        self._on_message = on_message

        self._app = (
            Application.builder()
            .token(self._config.bot_token)
            .http_version("1.1")
            .build()
        )

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        # Start polling
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(
            poll_interval=1.0,
            timeout=int(self._config.long_poll_timeout_seconds),
        )

        logger.info("Telegram adapter started, polling for updates")

    async def stop(self) -> None:
        """Stop the Telegram adapter."""
        if self._app is not None:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
        logger.info("Telegram adapter stopped")

    async def send_message(self, user: str, text: str) -> str:
        """Send a message to a Telegram chat. Returns message ID."""
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        chat_id = int(user)
        msg = await self._app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
        return str(msg.message_id)

    async def edit_message(self, user: str, msg_id: str, text: str) -> None:
        """Edit a message in-place, rate-limited to avoid 429s."""
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        # Rate limiting: max 1 edit per rate_limit_edits_seconds per message
        now = time.monotonic()
        last_edit = self._last_edit_times.get(msg_id, 0.0)
        elapsed = now - last_edit
        if elapsed < self._config.rate_limit_edits_seconds:
            wait = self._config.rate_limit_edits_seconds - elapsed
            await asyncio.sleep(wait)

        chat_id = int(user)
        try:
            await self._app.bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(msg_id),
                text=text,
                parse_mode="Markdown",
            )
            self._last_edit_times[msg_id] = time.monotonic()
        except Exception as e:
            # Telegram returns 400 if message content is unchanged
            if "message is not modified" in str(e).lower():
                logger.debug("Message %s not modified, skipping edit", msg_id)
            else:
                logger.warning("Failed to edit message %s: %s", msg_id, e)

    async def send_error(self, user: str, text: str) -> None:
        """Send an error message to a Telegram chat."""
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        chat_id = int(user)
        await self._app.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {text}",
        )

    def _is_allowed(self, user_id: int, username: str | None) -> bool:
        """Check if a user is in the allowed list."""
        if not self._config.allowed_users:
            return True  # No whitelist = allow all

        allowed = self._config.allowed_users
        return (
            str(user_id) in allowed
            or (username is not None and username in allowed)
        )

    async def _handle_start(self, update: Update, context) -> None:
        """Handle /start command."""
        if update.effective_user is None or update.effective_message is None:
            return

        if not self._is_allowed(update.effective_user.id, update.effective_user.username):
            await update.effective_message.reply_text("Not authorized.")
            return

        await update.effective_message.reply_text(
            "Hestia is running. Send me a message to start a conversation."
        )

    async def _handle_message(self, update: Update, context) -> None:
        """Handle incoming text messages."""
        if update.effective_user is None or update.effective_message is None:
            return
        if update.effective_message.text is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)

        if not self._is_allowed(user_id, username):
            await update.effective_message.reply_text("Not authorized.")
            return

        if self._on_message is not None:
            await self._on_message(
                self.name,
                str(user_id),
                update.effective_message.text,
            )
