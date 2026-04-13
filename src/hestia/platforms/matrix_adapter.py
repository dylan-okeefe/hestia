"""Matrix platform adapter using matrix-nio."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from nio import (
    AsyncClient,
    ErrorResponse,
    Event,
    MatrixRoom,
    MegolmEvent,
    RoomGetEventError,
    RoomMessageText,
    RoomSendResponse,
    SyncResponse,
)

from hestia.config import MatrixConfig
from hestia.platforms.base import IncomingMessageCallback, Platform

logger = logging.getLogger(__name__)


class MatrixAdapter(Platform):
    """Matrix platform adapter using matrix-nio.

    Design decisions:
    - One Matrix room = one Hestia session (room ID is platform_user)
    - allowed_rooms whitelist for security (empty = deny all)
    - Rate-limit edit_message to avoid homeserver abuse flags
    - Unencrypted rooms only for v1 (E2EE deferred)
    - HTML in formatted_body is stripped when feeding the model
    """

    def __init__(self, config: MatrixConfig) -> None:
        if not config.access_token:
            raise ValueError("Matrix access_token is required")
        if not config.user_id:
            raise ValueError("Matrix user_id is required")

        self._config = config
        self._client: AsyncClient | None = None
        self._on_message: IncomingMessageCallback | None = None
        self._last_edit_times: dict[str, float] = {}  # event_id -> last edit timestamp
        self._sync_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def name(self) -> str:
        return "matrix"

    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Start Matrix sync loop."""
        self._on_message = on_message
        self._stop_event = asyncio.Event()

        self._client = AsyncClient(
            homeserver=self._config.homeserver,
            user=self._config.user_id,
            device_id=self._config.device_id,
        )
        self._client.access_token = self._config.access_token

        # Register event callbacks
        self._client.add_event_callback(self._handle_room_message, RoomMessageText)

        # Start sync loop in background
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Matrix adapter started, user=%s", self._config.user_id)

    async def stop(self) -> None:
        """Stop the Matrix adapter."""
        if self._stop_event is not None:
            self._stop_event.set()

        if self._sync_task is not None:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        if self._client is not None:
            await self._client.close()
            self._client = None

        logger.info("Matrix adapter stopped")

    async def send_message(self, user: str, text: str) -> str:
        """Send a message to a Matrix room. Returns event ID."""
        if self._client is None:
            raise RuntimeError("Matrix adapter not started")

        room_id = user  # platform_user is the room ID
        content = {
            "msgtype": "m.text",
            "body": text,
        }

        response = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
        )

        if isinstance(response, RoomSendResponse):
            logger.debug("Sent message to %s, event_id=%s", room_id, response.event_id)
            return response.event_id
        else:
            logger.error("Failed to send message to %s: %s", room_id, response)
            raise RuntimeError(f"Failed to send message: {response}")

    async def edit_message(self, user: str, msg_id: str, text: str) -> None:
        """Edit a message in-place, rate-limited to avoid abuse flags."""
        if self._client is None:
            raise RuntimeError("Matrix adapter not started")

        # Rate limiting
        now = time.monotonic()
        last_edit = self._last_edit_times.get(msg_id, 0.0)
        elapsed = now - last_edit
        if elapsed < self._config.rate_limit_edits_seconds:
            wait = self._config.rate_limit_edits_seconds - elapsed
            await asyncio.sleep(wait)

        room_id = user
        content = {
            "msgtype": "m.text",
            "body": f"* {text}",  # Matrix edit convention
            "m.new_content": {
                "msgtype": "m.text",
                "body": text,
            },
            "m.relates_to": {
                "rel_type": "m.replace",
                "event_id": msg_id,
            },
        }

        response = await self._client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
        )

        if isinstance(response, RoomSendResponse):
            self._last_edit_times[msg_id] = time.monotonic()
            logger.debug("Edited message %s in %s", msg_id, room_id)
        else:
            logger.warning("Failed to edit message %s: %s", msg_id, response)

    async def send_error(self, user: str, text: str) -> None:
        """Send an error message to a Matrix room."""
        error_text = f"⚠️ Error: {text}"
        await self.send_message(user, error_text)

    def _is_allowed(self, room_id: str) -> bool:
        """Check if a room is in the allowed list."""
        if not self._config.allowed_rooms:
            return False  # Empty whitelist = deny all (secure default)
        return room_id in self._config.allowed_rooms

    async def _sync_loop(self) -> None:
        """Background sync loop."""
        assert self._client is not None
        assert self._stop_event is not None

        try:
            while not self._stop_event.is_set():
                try:
                    sync_response = await self._client.sync(
                        timeout=self._config.sync_timeout_ms,
                        since=self._client.next_batch,
                    )
                    if isinstance(sync_response, SyncResponse):
                        # Sync successful, next_batch updated by client
                        pass
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("Matrix sync error: %s", e)
                    await asyncio.sleep(5)  # Back off on error
        except asyncio.CancelledError:
            logger.debug("Matrix sync loop cancelled")
            raise

    async def _handle_room_message(
        self, room: MatrixRoom, event: RoomMessageText
    ) -> None:
        """Handle incoming room messages."""
        if self._on_message is None:
            return

        # Ignore our own messages
        if event.sender == self._config.user_id:
            return

        # Check room allowlist
        if not self._is_allowed(room.room_id):
            logger.debug("Ignoring message from non-allowed room %s", room.room_id)
            return

        # Get message body
        body = event.body
        if not body or not body.strip():
            return  # Ignore empty/whitespace messages

        # Strip HTML if formatted_body exists (we only want plain text for the model)
        # body is already plain text per matrix spec

        logger.debug(
            "Received message from %s in %s: %s",
            event.sender,
            room.room_id,
            body[:100],
        )

        # Call the orchestrator callback
        # platform_user is the room ID (one room = one session)
        await self._on_message(
            self.name,
            room.room_id,
            body.strip(),
        )
