"""Matrix platform adapter using matrix-nio."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessageText,
    RoomSendResponse,
    SyncResponse,
)

from hestia.commands.meta import get_default_registry, render_commands_reference
from hestia.commands.tour import (
    get_tour_store,
    render_tour_continue,
    render_tour_end,
    render_tour_start,
)
from hestia.config import MatrixConfig
from hestia.errors import PlatformError
from hestia.platforms.allowlist import (
    match_allowlist,
    validate_matrix_room_id,
)
from hestia.platforms.base import IncomingMessageCallback, Platform
from hestia.platforms.confirmation import ConfirmationStore, render_args_for_human_review

if TYPE_CHECKING:
    from hestia.orchestrator.compaction import SessionCompactor
    from hestia.persistence.session_store import SessionStore

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
        self._confirmation_store = ConfirmationStore()
        self._confirmation_timeout_seconds = 60.0
        # Maps original confirmation event_id -> request_id so we can correlate replies
        self._pending_confirmations: dict[str, str] = {}
        # Runtime deps are injected by run_platform after the orchestrator is built.
        self._session_store: SessionStore | None = None
        self._reset_callback: Callable[[str], Awaitable[None]] | None = None
        self._compactor: SessionCompactor | None = None

        # Validate allowed_rooms entries (warn, don't hard-fail, for backward compat)
        for entry in self._config.allowed_rooms:
            if "*" in entry or "?" in entry or "[" in entry:
                continue  # Wildcard patterns skip strict validation
            if validate_matrix_room_id(entry):
                continue
            logger.warning(
                "Matrix allowed_rooms entry %r does not look like a valid "
                "room ID or alias",
                entry,
            )

    @property
    def name(self) -> str:
        return "matrix"

    def set_session_store(self, session_store: SessionStore) -> None:
        """Inject session store for /reset command handling."""
        self._session_store = session_store

    def set_compactor(self, compactor: SessionCompactor) -> None:
        """Inject the session compactor for /compact handling."""
        self._compactor = compactor

    def register_reset_callback(
        self, callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """Register a callback invoked when /reset archives a session.

        The callback receives the platform_user whose session was reset so the
        runner can drop any in-memory session cache for that room.
        """
        self._reset_callback = callback

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

        # Initial sync to advance next_batch past existing timeline events,
        # so the message callback only fires for messages sent after start().
        await self._client.sync(timeout=5000)

        self._client.add_event_callback(self._handle_room_message, RoomMessageText)

        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Matrix adapter started, user=%s", self._config.user_id)

    async def stop(self) -> None:
        """Stop the Matrix adapter."""
        if self._stop_event is not None:
            self._stop_event.set()

        if self._sync_task is not None:
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task
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
            return str(response.event_id)
        else:
            logger.error("Failed to send message to %s: %s", room_id, response)
            raise PlatformError(f"Failed to send message: {response}")

    async def edit_message(
        self, user: str, msg_id: str, text: str, **kwargs: Any
    ) -> None:
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
            raise PlatformError(f"Failed to edit message: {response}")

    async def send_error(self, user: str, text: str) -> None:
        """Send an error message to a Matrix room."""
        error_text = f"⚠️ Error: {text}"
        await self.send_message(user, error_text)

    async def set_typing(self, user: str, typing: bool = True) -> None:
        """Set typing indicator in a Matrix room."""
        if self._client is None:
            return
        try:
            await self._client.room_typing(user, typing, timeout=30000 if typing else 0)
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed to set typing indicator: %s", e)

    async def delete_message(self, user: str, msg_id: str) -> None:
        """Redact (delete) a message from a Matrix room."""
        if self._client is None:
            return
        try:
            await self._client.room_redact(user, msg_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed to redact message %s: %s", msg_id, e)

    async def request_confirmation(
        self,
        user: str,
        tool_name: str,
        arguments: dict[str, Any],
        requester_platform_user: str | None = None,
        request_token: str | None = None,
    ) -> bool:
        """Post a confirmation prompt and wait for a 'yes'/'no' reply.

        Returns ``True`` on 'yes', ``False`` on 'no' or timeout.
        """
        if self._client is None:
            raise RuntimeError("Matrix adapter not started")

        prompt = render_args_for_human_review(tool_name, arguments)
        text = (
            f"🔒 Tool '{tool_name}' wants to run with: {prompt}. "
            f"Reply 'yes' or 'no' within {int(self._confirmation_timeout_seconds)}s."
        )

        event_id = await self.send_message(user, text)

        req = self._confirmation_store.create(
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=self._confirmation_timeout_seconds,
            requester_platform_user=requester_platform_user,
            request_token=request_token,
        )
        self._pending_confirmations[event_id] = req.id

        assert req.future is not None
        try:
            return await asyncio.wait_for(
                req.future, timeout=self._confirmation_timeout_seconds
            )
        except TimeoutError:
            self._confirmation_store.cancel(req.id)
            return False
        finally:
            self._pending_confirmations.pop(event_id, None)

    def _is_allowed(self, room_id: str) -> bool:
        """Check if a room is in the allowed list.

        Empty whitelist = deny all (secure default).
        Supports wildcards: ``*`` matches any sequence, ``?`` matches one character.
        """
        allowed = self._config.allowed_rooms
        if not allowed:
            return False
        return match_allowlist(allowed, room_id, case_sensitive=True)

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
                except Exception as e:  # noqa: BLE001 — background sync loop — intentionally broad
                    logger.warning("Matrix sync error: %s", e)
                    await asyncio.sleep(5)  # Back off on error
        except asyncio.CancelledError:
            logger.debug("Matrix sync loop cancelled")
            raise

    async def _handle_room_message(
        self, room: MatrixRoom, event: RoomMessageText
    ) -> None:
        """Handle incoming room messages."""
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

        stripped_body = body.strip()

        # Handle local slash commands before routing to the orchestrator
        lower_body = stripped_body.lower()
        if lower_body.startswith("/reset"):
            await self._handle_reset(room, event)
            return
        if lower_body.startswith("/compact"):
            await self._handle_compact(room, event)
            return
        if lower_body.startswith("/commands") or lower_body.startswith("/help"):
            await self._handle_commands(room, event)
            return
        if lower_body.startswith("/tour"):
            await self._handle_tour(room, event)
            return
        if lower_body.startswith("/continue"):
            await self._handle_continue(room, event)
            return
        if lower_body.startswith("/endtour"):
            await self._handle_endtour(room, event)
            return

        # Check if this is a reply to a pending confirmation (internal adapter concern)
        in_reply_to = self._extract_in_reply_to(event)
        if in_reply_to and in_reply_to in self._pending_confirmations:
            request_id = self._pending_confirmations[in_reply_to]
            reply_text = stripped_body.lower()
            approver = event.sender
            if reply_text in ("yes", "y"):
                self._confirmation_store.resolve(request_id, True, approver)
            elif reply_text in ("no", "n"):
                self._confirmation_store.resolve(request_id, False, approver)
            # Don't route confirmation replies to the orchestrator
            return

        # Check for pending workflow interactive responses
        from hestia.workflows.response_store import DEFAULT_RESPONSE_STORE

        pending_request_id = DEFAULT_RESPONSE_STORE.find_pending("matrix", room.room_id)
        if pending_request_id is not None:
            resolved = DEFAULT_RESPONSE_STORE.resolve(pending_request_id, stripped_body)
            if resolved:
                # Don't route workflow replies to the orchestrator
                return

        if self._on_message is None:
            return

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
        # sender_platform_user is the individual Matrix user id that sent the event
        await self._on_message(
            self.name,
            room.room_id,
            stripped_body,
            event.sender,
            None,
        )

    async def _handle_reset(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle /reset command: archive the active session and clear the cache."""
        platform_user = room.room_id

        if self._session_store is None:
            logger.warning("Reset requested in %s but session store not injected", platform_user)
            await self.send_message(platform_user, "Reset is not available right now.")
            return

        session = await self._session_store.get_active_session("matrix", platform_user)
        if session is None:
            await self.send_message(
                platform_user,
                "No active conversation to reset. You're already starting fresh.",
            )
            return

        await self._session_store.archive_session(session.id)

        if self._reset_callback is not None:
            try:
                await self._reset_callback(platform_user)
            except Exception:
                logger.exception("Reset callback failed for %s", platform_user)

        await self.send_message(
            platform_user,
            "Conversation reset. Previous context was archived; your next message starts a fresh session.",
        )

    async def _handle_compact(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle /compact command: summarize, archive, and shrink history in place."""
        platform_user = room.room_id

        if self._session_store is None or self._compactor is None:
            logger.warning("Compact requested in %s but deps not injected", platform_user)
            await self.send_message(platform_user, "Compact is not available right now.")
            return

        session = await self._session_store.get_active_session("matrix", platform_user)
        if session is None:
            await self.send_message(
                platform_user,
                "No active conversation to compact.",
            )
            return

        body = event.body.strip()
        instruction = None
        if " " in body:
            _, instruction = body.split(None, 1)

        await self.send_message(platform_user, "Compacting session...")
        outcome = await self._compactor.compact(session.id, instruction=instruction)
        await self.send_message(platform_user, outcome.message)

    async def _handle_commands(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle /commands and /help: render the registry catalog."""
        platform_user = room.room_id
        text = render_commands_reference(get_default_registry())
        await self.send_message(platform_user, text)

    async def _handle_tour(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle /tour: Matrix rooms are treated as group chats, so reply DM-only."""
        platform_user = room.room_id
        text = render_tour_start(
            get_tour_store(), "matrix", platform_user, group_room=True
        )
        await self.send_message(platform_user, text)

    async def _handle_continue(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle /continue: behaves as outside a tour in a Matrix room."""
        platform_user = room.room_id
        text = render_tour_continue(
            get_tour_store(), "matrix", platform_user, group_room=True
        )
        await self.send_message(platform_user, text)

    async def _handle_endtour(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Handle /endtour: behaves as outside a tour in a Matrix room."""
        platform_user = room.room_id
        text = render_tour_end(
            get_tour_store(), "matrix", platform_user, group_room=True
        )
        await self.send_message(platform_user, text)

    @staticmethod
    def _extract_in_reply_to(event: RoomMessageText) -> str | None:
        """Extract the event_id this message is replying to, if any."""
        try:
            source: dict[str, Any] = event.source
            content = source.get("content", {})
            if not isinstance(content, dict):
                return None
            relates_to = content.get("m.relates_to", {})
            if not isinstance(relates_to, dict):
                return None
            in_reply_to = relates_to.get("m.in_reply_to", {})
            if not isinstance(in_reply_to, dict):
                return None
            event_id = in_reply_to.get("event_id")
            return event_id if isinstance(event_id, str) else None
        except Exception:  # noqa: BLE001
            return None
