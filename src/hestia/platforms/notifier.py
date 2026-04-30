"""Platform notifier for sending push notifications from scheduled tasks."""

from __future__ import annotations

import logging
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

    async def _send_telegram(self, platform_user: str, text: str) -> bool:
        token = self._config.telegram.bot_token
        if not token:
            logger.debug("Telegram bot token not configured, skipping notification")
            return False
        try:
            from telegram import Bot

            bot = Bot(token)
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
                txn_id = hash(text) & 0xFFFFFFFF
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
