"""Telegram platform adapter."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from hestia.config import TelegramConfig
from hestia.platforms.base import IncomingMessageCallback, Platform
from hestia.platforms.confirmation import ConfirmationStore, render_args_for_human_review

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
        self._app: Application[Any, Any, Any, Any, Any, Any] | None = None
        self._on_message: IncomingMessageCallback | None = None
        self._last_edit_times: dict[str, float] = {}  # msg_id -> last edit timestamp
        self._confirmation_store = ConfirmationStore()
        self._confirmation_timeout_seconds = 60.0

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Start polling for Telegram messages."""
        self._on_message = on_message

        self._app = Application.builder().token(self._config.bot_token).http_version("1.1").build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback_query))

        # Start polling
        await self._app.initialize()
        await self._app.start()
        if self._app.updater is None:
            raise RuntimeError("Telegram application updater is not available")
        await self._app.updater.start_polling(
            poll_interval=1.0,
            timeout=int(self._config.long_poll_timeout_seconds),
        )

        logger.info("Telegram adapter started, polling for updates")

    async def stop(self) -> None:
        """Stop the Telegram adapter."""
        if self._app is not None:
            if self._app.updater is not None:
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
        except TelegramError as e:
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

    async def request_confirmation(
        self, user: str, tool_name: str, arguments: dict[str, Any]
    ) -> bool:
        """Send an inline-keyboard confirmation prompt and wait for operator response.

        Returns ``True`` on ✅, ``False`` on ❌ or timeout.
        """
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        chat_id = int(user)
        prompt = render_args_for_human_review(tool_name, arguments)
        text = (
            f"🔒 Tool *{tool_name}* wants to run:\n"
            f"```json\n{prompt}\n```\n"
            f"Approve within {int(self._confirmation_timeout_seconds)}s?"
        )

        req = self._confirmation_store.create(
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=self._confirmation_timeout_seconds,
        )

        keyboard = [
            [
                InlineKeyboardButton("✅", callback_data=f"confirm:{req.id}:yes"),
                InlineKeyboardButton("❌", callback_data=f"confirm:{req.id}:no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self._app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

        assert req.future is not None
        try:
            return await asyncio.wait_for(
                req.future, timeout=self._confirmation_timeout_seconds
            )
        except asyncio.TimeoutError:
            self._confirmation_store.cancel(req.id)
            return False

    def _is_allowed(self, user_id: int, username: str | None) -> bool:
        """Check if a user is in the allowed list.

        Empty list = deny all (require explicit opt-in).
        """
        if not self._config.allowed_users:
            return False

        allowed = self._config.allowed_users
        return str(user_id) in allowed or (username is not None and username in allowed)

    async def _handle_start(self, update: Update, context: Any) -> None:
        """Handle /start command."""
        if update.effective_user is None or update.effective_message is None:
            return

        if not self._is_allowed(update.effective_user.id, update.effective_user.username):
            await update.effective_message.reply_text("Not authorized.")
            return

        await update.effective_message.reply_text(
            "Hestia is running. Send me a message to start a conversation."
        )

    async def _handle_message(self, update: Update, context: Any) -> None:
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

    async def _handle_callback_query(self, update: Update, context: Any) -> None:
        """Handle inline-keyboard button presses for confirmations."""
        if update.callback_query is None or update.callback_query.data is None:
            return

        data = update.callback_query.data
        if not data.startswith("confirm:"):
            return

        parts = data.split(":")
        if len(parts) != 3:
            await update.callback_query.answer("Invalid confirmation.")
            return

        _prefix, request_id, answer = parts
        approved = answer == "yes"

        resolved = self._confirmation_store.resolve(request_id, approved)

        if resolved:
            await update.callback_query.answer(
                "Approved." if approved else "Cancelled."
            )
            # Update the original message to remove the keyboard
            msg = update.callback_query.message
            if msg is not None:
                try:
                    original_text = getattr(msg, "text", None) or ""
                    # Strip the "Approve within ...?" line
                    lines = original_text.split("\n")
                    new_lines = [ln for ln in lines if not ln.startswith("Approve")]
                    new_text = "\n".join(new_lines)
                    status = "✅ Approved" if approved else "❌ Denied"
                    await update.callback_query.edit_message_text(
                        text=f"{status}\n{new_text}",
                        parse_mode="Markdown",
                    )
                except TelegramError as e:
                    logger.debug("Failed to update confirmation message: %s", e)
        else:
            await update.callback_query.answer("This confirmation has expired.")
