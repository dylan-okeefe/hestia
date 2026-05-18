"""Platform notifier for sending push notifications from scheduled tasks."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hestia.config import HestiaConfig

logger = logging.getLogger(__name__)


class PlatformNotifier:
    """Sends push notifications to platform users without full adapter lifecycle.

    This is a lightweight send-only client used by the scheduler daemon to
    deliver scheduled task results to Telegram, Matrix, etc. It does not
    start polling loops or maintain persistent connections.
    """

    def __init__(self, config: HestiaConfig) -> None:
        self._config = config
        self._telegram_bot: Any | None = None  # lazy init

    async def send(self, platform: str, platform_user: str, text: str) -> bool:
        """Send a notification to a platform user.

        Args:
            platform: Platform name (e.g., "telegram", "matrix")
            platform_user: Platform-specific user identifier
            text: Message text to send

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if platform == "telegram":
            return await self._send_telegram(platform_user, text)
        if platform == "matrix":
            return await self._send_matrix(platform_user, text)
        logger.debug("No notifier available for platform %r", platform)
        return False

    async def send_interactive(
        self,
        platform: str,
        platform_user: str,
        text: str,
        buttons: list[str],
        request_id: str,
    ) -> bool:
        """Send an interactive message with reply buttons.

        Args:
            platform: Platform name.
            platform_user: Platform-specific user identifier.
            text: Message text.
            buttons: Button labels.
            request_id: Unique request ID embedded in callback data.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if platform == "telegram":
            return await self._send_telegram_interactive(
                platform_user, text, buttons, request_id
            )
        # Fallback to plain text for other platforms
        button_text = " / ".join(buttons)
        full_text = f"{text}\n\nReply with one of: {button_text}"
        return await self.send(platform, platform_user, full_text)

    def _get_telegram_bot(self) -> Any:
        """Return a cached telegram.Bot instance, creating it on first use."""
        if self._telegram_bot is None:
            from telegram import Bot

            self._telegram_bot = Bot(token=self._config.telegram.bot_token)
        return self._telegram_bot

    async def _send_telegram_interactive(
        self, platform_user: str, text: str, buttons: list[str], request_id: str
    ) -> bool:
        token = self._config.telegram.bot_token
        if not token:
            logger.debug("Telegram bot token not configured, skipping interactive message")
            return False
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            bot = self._get_telegram_bot()
            keyboard = [
                [
                    InlineKeyboardButton(
                        label, callback_data=f"workflow:{request_id}:{label}"
                    )
                ]
                for label in buttons
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await bot.send_message(
                chat_id=int(platform_user),
                text=text,
                reply_markup=reply_markup,
            )
            logger.debug(
                "Sent interactive Telegram message to %s (request %s)",
                platform_user,
                request_id,
            )
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to send interactive Telegram message to %s", platform_user
            )
            return False

    async def _send_telegram(self, platform_user: str, text: str) -> bool:
        token = self._config.telegram.bot_token
        if not token:
            logger.debug("Telegram bot token not configured, skipping notification")
            return False
        try:
            bot = self._get_telegram_bot()
            await bot.send_message(chat_id=int(platform_user), text=text)
            logger.debug("Sent Telegram notification to %s", platform_user)
            return True
        except Exception:  # noqa: BLE001
            # Platform notifications are best-effort; log and continue.
            logger.exception("Failed to send Telegram notification to %s", platform_user)
            return False

    async def _send_matrix(self, platform_user: str, text: str) -> bool:
        cfg = self._config.matrix
        if not cfg or not cfg.homeserver or not cfg.access_token:
            logger.debug("Matrix not configured, skipping notification")
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                room_id = platform_user
                txn_id = uuid.uuid4().hex[:16]
                url = (
                    f"{cfg.homeserver}/_matrix/client/v3/rooms/{room_id}"
                    f"/send/m.room.message/txn{txn_id}"
                )
                response = await client.put(
                    url,
                    headers={"Authorization": f"Bearer {cfg.access_token}"},
                    json={
                        "msgtype": "m.text",
                        "body": text,
                    },
                )
                response.raise_for_status()
                logger.debug("Sent Matrix notification to %s", platform_user)
                return True
        except Exception:  # noqa: BLE001
            # Platform notifications are best-effort; log and continue.
            logger.exception("Failed to send Matrix notification to %s", platform_user)
            return False

    async def close(self) -> None:
        """Release resources held by the notifier (e.g., the cached Telegram bot)."""
        if self._telegram_bot is not None:
            try:
                await self._telegram_bot.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to shutdown Telegram bot")
            self._telegram_bot = None
