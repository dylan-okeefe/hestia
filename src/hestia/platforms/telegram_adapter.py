"""Telegram platform adapter."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from hestia.commands.meta import get_default_registry, render_commands_reference
from hestia.commands.tour import (
    get_tour_store,
    render_tour_continue,
    render_tour_end,
    render_tour_start,
)
from hestia.config import TelegramConfig
from hestia.core.types import Message as HestiaMessage
from hestia.orchestrator.finalization import sanitize_user_error
from hestia.orchestrator.types import StreamCallback
from hestia.platforms.allowlist import (
    match_allowlist,
    validate_telegram_user_id,
    validate_telegram_username,
)
from hestia.platforms.base import IncomingMessageCallback, Platform
from hestia.platforms.confirmation import ConfirmationStore, render_args_for_human_review
from hestia.policy.channel import Channel
from hestia.voice.pipeline import get_voice_pipeline

if TYPE_CHECKING:
    from hestia.config import VoiceConfig
    from hestia.orchestrator.compaction import SessionCompactor
    from hestia.orchestrator.engine import Orchestrator
    from hestia.orchestrator.handoff_service import HandoffService
    from hestia.persistence.session_store import SessionStore


# Telegram caps a single message at 4096 characters. We leave headroom for
# the HTML tags added by _md_to_tg_html by splitting the raw Markdown text at
# a conservative limit and sending/editing in chunks.
_TELEGRAM_MAX_TEXT_LEN = 4096
_SAFE_CHUNK_LEN = 3800


def _split_long_text(text: str, max_len: int = _SAFE_CHUNK_LEN) -> list[str]:
    """Split ``text`` into chunks that fit Telegram's message length limit.

    Prefers splitting at paragraph boundaries, then lines, then sentences,
    then words, falling back to a hard split at ``max_len``.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_len:
        chunk = remaining[:max_len]

        # Prefer paragraph boundary
        split_at = chunk.rfind("\n\n")
        if split_at > max_len // 4:
            split_at += 2
        else:
            # Then line boundary
            split_at = chunk.rfind("\n")
            if split_at > max_len // 4:
                split_at += 1
            else:
                # Then sentence boundary
                split_at = max(
                    chunk.rfind(". "),
                    chunk.rfind("! "),
                    chunk.rfind("? "),
                )
                if split_at > max_len // 4:
                    split_at += 2
                else:
                    # Then word boundary
                    split_at = chunk.rfind(" ")
                    if split_at > max_len // 4:
                        split_at += 1
                    else:
                        split_at = max_len

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _md_to_tg_html(text: str) -> str:
    """Convert basic Markdown to Telegram HTML parse_mode.

    Handles **bold**, *italic*, `inline code`, and ```code blocks```.
    Escapes HTML entities to avoid parse errors.
    """

    # 1. Escape HTML special chars
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 2. Triple backtick code blocks
    text = re.sub(
        r"```(\w*)\n(.*?)\n```",
        lambda m: f"<pre><code class=\"language-{m.group(1)}\">{m.group(2)}</code></pre>",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"```(.*?)```",
        r"<pre>\1</pre>",
        text,
        flags=re.DOTALL,
    )

    # 3. Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 4. Bold (**text**)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    # 5. Italic (*text*) — only if not already inside <b> tags and not double asterisks
    def _italic_repl(m: re.Match[str]) -> str:
        inner = m.group(1)
        # Skip if it already contains bold tags (can happen with nested patterns)
        if "<b>" in inner or "</b>" in inner:
            return m.group(0)
        return f"<i>{inner}</i>"

    text = re.sub(r"\*([^*\n]+)\*", _italic_repl, text)

    return text


logger = logging.getLogger(__name__)

# Default TTS PCM16 mono sample rate. The active voice config may override this
# (e.g. Kokoro outputs 24000 Hz).
_DEFAULT_TTS_SAMPLE_RATE = 22050


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
        self._last_edit_max_age = 3600.0  # 1 hour TTL
        self._confirmation_store = ConfirmationStore()
        self._confirmation_timeout_seconds = 60.0
        # Identity ContextVars wired by the runner (set_confirmation_context)
        # so paths that bypass PlatformRunner — voice turns — can still bind
        # requester identity for confirmations and channel attribution.
        self._user_context_var: ContextVar[str] | None = None
        self._requester_context_var: ContextVar[str | None] | None = None
        self._stream_states: dict[str, dict[str, Any]] = {}

        # Background tasks that keep the typing indicator alive (refreshed every 4s).
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}

        # Runtime deps are injected by run_platform after the orchestrator is built.
        self._orchestrator: Orchestrator | None = None
        self._session_store: SessionStore | None = None
        self._handoff_service: HandoffService | None = None
        self._system_prompt: str = ""
        self._voice_config: VoiceConfig | None = None
        self._reset_callback: Callable[[str], Awaitable[None]] | None = None
        self._compactor: SessionCompactor | None = None

        # Validate allowed_users entries (hard-fail at startup)
        for entry in self._config.allowed_users:
            if "*" in entry or "?" in entry or "[" in entry:
                continue  # Wildcard patterns skip strict validation
            if validate_telegram_user_id(entry):
                continue
            if validate_telegram_username(entry):
                continue
            raise ValueError(
                f"Invalid allowed_users entry {entry!r}: must be a numeric "
                "Telegram user ID or a valid username."
            )

    @property
    def name(self) -> str:
        return "telegram"

    def set_voice_deps(
        self,
        orchestrator: Orchestrator,
        session_store: SessionStore,
        handoff_service: HandoffService,
        system_prompt: str,
        voice_config: VoiceConfig | None,
    ) -> None:
        """Inject orchestrator, session store, and handoff service.

        Called by run_platform after the orchestrator is built.
        """
        self._orchestrator = orchestrator
        self._session_store = session_store
        self._handoff_service = handoff_service
        self._system_prompt = system_prompt
        self._voice_config = voice_config

    def _tts_sample_rate(self) -> int:
        """Return the TTS output sample rate from the voice config."""
        if self._voice_config is not None:
            return self._voice_config.tts_sample_rate
        return _DEFAULT_TTS_SAMPLE_RATE

    def register_reset_callback(
        self, callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """Register a callback invoked when /reset archives a session.

        The callback receives the platform_user whose session was reset so the
        runner can drop any in-memory session cache for that user.
        """
        self._reset_callback = callback

    def set_compactor(self, compactor: SessionCompactor) -> None:
        """Inject the session compactor for /compact handling."""
        self._compactor = compactor

    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Start polling for Telegram messages."""
        self._on_message = on_message

        self._app = Application.builder().token(self._config.bot_token).http_version("1.1").build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("reset", self._handle_reset))
        self._app.add_handler(CommandHandler("compact", self._handle_compact))
        self._app.add_handler(CommandHandler("commands", self._handle_commands))
        self._app.add_handler(CommandHandler("help", self._handle_help))
        self._app.add_handler(CommandHandler("tour", self._handle_tour))
        self._app.add_handler(CommandHandler("continue", self._handle_continue))
        self._app.add_handler(CommandHandler("endtour", self._handle_endtour))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        if self._config.voice_messages:
            self._app.add_handler(MessageHandler(filters.VOICE, self._handle_voice_message))
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
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        if self._app is not None:
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
        logger.info("Telegram adapter stopped")

    async def _send_chunk(
        self, chat_id: int, text: str, *, parse_mode: str = "HTML"
    ) -> Any:
        """Send one chunk, falling back to plain text if HTML parse fails.

        Sleeps and retries once on Telegram flood-control (RetryAfter).
        """
        assert self._app is not None
        try:
            return await self._app.bot.send_message(
                chat_id=chat_id,
                text=_md_to_tg_html(text),
                parse_mode=parse_mode,
            )
        except RetryAfter as e:
            logger.warning(
                "Telegram flood control for chat %s; sleeping %ss then retrying",
                chat_id,
                e.retry_after,
            )
            retry_after = (
                e.retry_after.total_seconds()
                if isinstance(e.retry_after, timedelta)
                else e.retry_after
            )
            await asyncio.sleep(retry_after)
            return await self._app.bot.send_message(
                chat_id=chat_id,
                text=_md_to_tg_html(text),
                parse_mode=parse_mode,
            )
        except TelegramError as e:
            if "can't parse entities" in str(e).lower():
                logger.warning(
                    "HTML parse failed for chunk, retrying as plain text: %s", e
                )
                return await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=None,
                )
            logger.warning(
                "Telegram send failed for chat %s (%d chars): %s",
                chat_id,
                len(text),
                e,
            )
            raise

    async def send_message(self, user: str, text: str) -> str:
        """Send a message to a Telegram chat. Returns message ID.

        Long messages are split into multiple Telegram messages; the first
        message ID is returned. If a chunk fails HTML parsing it is retried as
        plain text.
        """
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        chat_id = int(user)
        chunks = _split_long_text(text)
        first_msg = None
        for chunk in chunks:
            msg = await self._send_chunk(chat_id, chunk)
            if first_msg is None:
                first_msg = msg
        assert first_msg is not None
        return str(first_msg.message_id)

    def _prune_last_edit_times(self) -> None:
        """Evict entries older than _last_edit_max_age to prevent unbounded growth."""
        cutoff = time.monotonic() - self._last_edit_max_age
        stale = [k for k, v in self._last_edit_times.items() if v < cutoff]
        for k in stale:
            del self._last_edit_times[k]

    async def edit_message(
        self, user: str, msg_id: str, text: str, **kwargs: Any
    ) -> None:
        """Edit a message in-place, rate-limited to avoid 429s.

        If the new text exceeds Telegram's message length limit, the first
        chunk replaces the original message and any remaining chunks are sent
        as new messages.
        """
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        fallback_to_new_message = bool(kwargs.get("fallback_to_new_message", False))
        self._prune_last_edit_times()

        # Rate limiting: max 1 edit per rate_limit_edits_seconds per message
        now = time.monotonic()
        last_edit = self._last_edit_times.get(msg_id, 0.0)
        elapsed = now - last_edit
        if elapsed < self._config.rate_limit_edits_seconds:
            wait = self._config.rate_limit_edits_seconds - elapsed
            await asyncio.sleep(wait)

        chat_id = int(user)
        chunks = _split_long_text(text)
        edit_ok = False
        try:
            try:
                await self._edit_message_text(
                    chat_id=chat_id,
                    message_id=int(msg_id),
                    text=chunks[0],
                )
            except TelegramError as e:
                if "can't parse entities" in str(e).lower():
                    logger.warning(
                        "HTML parse failed for edit, retrying as plain text: %s", e
                    )
                    await self._edit_message_text(
                        chat_id=chat_id,
                        message_id=int(msg_id),
                        text=chunks[0],
                        parse_mode=None,
                    )
                else:
                    raise
            self._last_edit_times[msg_id] = time.monotonic()
            edit_ok = True
            for chunk in chunks[1:]:
                await self._send_chunk(chat_id, chunk)
        except TelegramError as e:
            # Telegram returns 400 if message content is unchanged
            if "message is not modified" in str(e).lower():
                logger.debug("Message %s not modified, skipping edit", msg_id)
                edit_ok = True
            else:
                logger.warning(
                    "Failed to edit message %s (%d chars): %s",
                    msg_id,
                    len(text),
                    e,
                )
                if fallback_to_new_message:
                    logger.info(
                        "Falling back to sending %d chunk(s) as new messages",
                        len(chunks),
                    )
                    for chunk in chunks:
                        await self._send_chunk(chat_id, chunk)
                    edit_ok = True
        if not edit_ok and fallback_to_new_message:
            # Safety net: if any other path left edit_ok False, send anyway.
            for chunk in chunks:
                await self._send_chunk(chat_id, chunk)

    async def _edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = "HTML",
    ) -> None:
        """Edit a message, sleeping and retrying once on flood control."""
        assert self._app is not None
        try:
            await self._app.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=_md_to_tg_html(text) if parse_mode == "HTML" else text,
                parse_mode=parse_mode,
            )
        except RetryAfter as e:
            logger.warning(
                "Telegram flood control for message %s; sleeping %ss then retrying",
                message_id,
                e.retry_after,
            )
            retry_after = (
                e.retry_after.total_seconds()
                if isinstance(e.retry_after, timedelta)
                else e.retry_after
            )
            await asyncio.sleep(retry_after)
            await self._app.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=_md_to_tg_html(text) if parse_mode == "HTML" else text,
                parse_mode=parse_mode,
            )

    async def send_error(self, user: str, text: str) -> None:
        """Send an error message to a Telegram chat."""
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        chat_id = int(user)
        await self._app.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {_md_to_tg_html(text)}",
            parse_mode="HTML",
        )

    async def set_typing(self, user: str, typing: bool = True) -> None:
        """Set typing indicator on Telegram (best-effort).

        Telegram's typing indicator expires after ~5 seconds, so we start a
        background task that refreshes it every 4 seconds while ``typing=True``.
        """
        if self._app is None:
            return

        # Cancel any existing refresh task for this user.
        existing = self._typing_tasks.pop(user, None)
        if existing is not None:
            existing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await existing

        if not typing:
            return

        async def _refresh() -> None:
            while True:
                try:
                    await self._app.bot.send_chat_action(  # type: ignore[union-attr]
                        chat_id=int(user),
                        action="typing",
                    )
                except TelegramError:
                    break
                await asyncio.sleep(4.0)

        self._typing_tasks[user] = asyncio.create_task(_refresh())

    def _make_stream_callback(self, chat_id: str) -> StreamCallback:
        """Create a streaming callback for progressive message delivery.

        Buffers the first chunk until at least 20 characters have been
        accumulated or 500 ms have elapsed, then sends a new message.
        Subsequent chunks trigger rate-limited in-place edits (max one
        edit per config.rate_limit_edits_seconds per message).

        The callback never raises: a Telegram error during streaming is
        logged and streaming continues. The final ``respond`` callback will
        deliver the complete text, either by editing the streamed message or
        by sending it as a new message if editing failed.
        """
        state: dict[str, Any] = {
            "accumulated": "",
            "message_id": None,
            "last_edit": 0.0,
            "first_chunk_time": None,
            "last_text": "",
        }
        self._stream_states[chat_id] = state
        min_edit_interval = self._config.rate_limit_edits_seconds

        async def callback(chunk: str) -> None:
            state["accumulated"] += chunk

            if state["message_id"] is None:
                if state["first_chunk_time"] is None:
                    state["first_chunk_time"] = time.monotonic()

                elapsed = time.monotonic() - state["first_chunk_time"]
                if len(state["accumulated"]) >= 20 or elapsed >= 0.5:
                    try:
                        state["message_id"] = await self.send_message(
                            chat_id, state["accumulated"]
                        )
                        state["last_edit"] = time.monotonic()
                        state["last_text"] = state["accumulated"]
                    except Exception as e:  # noqa: BLE001 — progressive delivery boundary
                        logger.warning(
                            "Failed to send initial streamed message to %s: %s",
                            chat_id,
                            e,
                        )
                return

            now = time.monotonic()
            if now - state["last_edit"] >= min_edit_interval:
                current = state["accumulated"]
                if current == state["last_text"]:
                    # Nothing changed since the last successful edit; skip the
                    # API call to avoid Telegram's "message is not modified" 400.
                    return
                try:
                    await self.edit_message(chat_id, state["message_id"], current)
                    state["last_edit"] = now
                    state["last_text"] = current
                except Exception as e:  # noqa: BLE001 — progressive delivery boundary
                    logger.warning(
                        "Failed to edit streamed message %s for %s: %s",
                        state["message_id"],
                        chat_id,
                        e,
                    )

        return callback

    def set_confirmation_context(
        self,
        user_var: ContextVar[str],
        requester_var: ContextVar[str | None],
    ) -> None:
        """Bind the runner's identity ContextVars (voice-turn support)."""
        self._user_context_var = user_var
        self._requester_context_var = requester_var

    async def request_confirmation(
        self,
        user: str,
        tool_name: str,
        arguments: dict[str, Any],
        requester_platform_user: str | None = None,
        request_token: str | None = None,
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
            requester_platform_user=requester_platform_user,
            request_token=request_token,
        )

        keyboard = [
            [
                InlineKeyboardButton("✅", callback_data=f"confirm:{req.id}:yes"),
                InlineKeyboardButton("❌", callback_data=f"confirm:{req.id}:no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except TelegramError as e:
            # BUG-015: raw tool arguments routinely contain markdown
            # metacharacters; unbalanced entities make Telegram reject the
            # message with "can't parse entities", which used to fail the
            # gated tool outright. Fall back to plain text — the JSON block
            # is still perfectly readable.
            logger.warning(
                "Markdown confirmation prompt rejected (%s); retrying as plain text",
                e,
            )
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔒 Tool {tool_name} wants to run:\n"
                    f"{prompt}\n"
                    f"Approve within {int(self._confirmation_timeout_seconds)}s?"
                ),
                reply_markup=reply_markup,
            )

        assert req.future is not None
        try:
            return await asyncio.wait_for(
                req.future, timeout=self._confirmation_timeout_seconds
            )
        except TimeoutError:
            self._confirmation_store.cancel(req.id)
            return False

    def _is_allowed(self, user_id: int, username: str | None) -> bool:
        """Check if a user is in the allowed list.

        Empty list = deny all (require explicit opt-in).
        Supports wildcards: ``*`` matches any sequence, ``?`` matches one character.
        Username matching is case-insensitive; numeric ID matching is case-sensitive.
        """
        allowed = self._config.allowed_users
        if not allowed:
            return False

        if username is not None:
            # BUG-064: validation strips '@' from configured usernames, so an
            # operator's '@alice' entry can never match PTB usernames (which
            # never contain '@'). Compare against the bare form defensively.
            bare_username = username.lstrip("@")
            normalized_patterns = [entry.lstrip("@") for entry in allowed]
            id_match = match_allowlist(allowed, str(user_id), case_sensitive=True)
            name_match = match_allowlist(
                normalized_patterns, bare_username, case_sensitive=False
            )
            return id_match or name_match
        return match_allowlist(allowed, str(user_id), case_sensitive=True)

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

    async def _handle_reset(self, update: Update, context: Any) -> None:
        """Handle /reset command: archive the active session and clear the cache."""
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        if self._session_store is None or self._handoff_service is None:
            await update.effective_message.reply_text(
                "Reset is not available right now (session store not connected)."
            )
            return

        if in_group:
            assert chat is not None
            platform_user = str(chat.id)
        else:
            platform_user = str(user_id)
        session = await self._session_store.get_active_session("telegram", platform_user)

        if session is None:
            await update.effective_message.reply_text(
                "No active conversation to reset. You're already starting fresh."
            )
            return

        await self._handoff_service.generate_handoff_summary(session.id)

        if self._reset_callback is not None:
            try:
                await self._reset_callback(platform_user)
            except Exception:
                logger.exception("Reset callback failed for %s", platform_user)

        await update.effective_message.reply_text(
            "Conversation reset. Previous context was archived; your next message starts a fresh session."
        )

    async def _handle_compact(self, update: Update, context: Any) -> None:
        """Handle /compact command: summarize, archive, and shrink history in place."""
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        if self._session_store is None or self._compactor is None:
            await update.effective_message.reply_text(
                "Compact is not available right now."
            )
            return

        if in_group:
            assert chat is not None
            platform_user = str(chat.id)
        else:
            platform_user = str(user_id)

        session = await self._session_store.get_active_session("telegram", platform_user)
        if session is None:
            await update.effective_message.reply_text(
                "No active conversation to compact."
            )
            return

        instruction = " ".join(context.args) if context and context.args else None

        status_msg = await update.effective_message.reply_text("Compacting session...")
        outcome = await self._compactor.compact(session.id, instruction=instruction)
        try:
            await self.edit_message(
                platform_user, str(status_msg.message_id), outcome.message
            )
        except TelegramError:
            await update.effective_message.reply_text(outcome.message)

    async def _handle_commands(self, update: Update, context: Any) -> None:
        """Handle /commands: render the registry catalog."""
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        # Render the catalog from the registry so /help and /commands share one source.
        text = render_commands_reference(get_default_registry())
        await update.effective_message.reply_text(text)

    async def _handle_help(self, update: Update, context: Any) -> None:
        """Handle /help: alias for /commands."""
        await self._handle_commands(update, context)

    async def _handle_tour(self, update: Update, context: Any) -> None:
        """Handle /tour: start the narrated tour, but not in group chats."""
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        if in_group:
            assert chat is not None
            platform_user = str(chat.id)
        else:
            platform_user = str(user_id)
        text = render_tour_start(
            get_tour_store(), "telegram", platform_user, group_room=in_group
        )
        await update.effective_message.reply_text(text)

    async def _handle_continue(self, update: Update, context: Any) -> None:
        """Handle /continue: advance the narrated tour by one step."""
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        if in_group:
            assert chat is not None
            platform_user = str(chat.id)
        else:
            platform_user = str(user_id)
        text = render_tour_continue(
            get_tour_store(), "telegram", platform_user, group_room=in_group
        )
        await update.effective_message.reply_text(text)

    async def _handle_endtour(self, update: Update, context: Any) -> None:
        """Handle /endtour: clear the active tour cursor."""
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        if in_group:
            assert chat is not None
            platform_user = str(chat.id)
        else:
            platform_user = str(user_id)
        text = render_tour_end(
            get_tour_store(), "telegram", platform_user, group_room=in_group
        )
        await update.effective_message.reply_text(text)

    async def _handle_message(self, update: Update, context: Any) -> None:
        """Handle incoming text messages."""
        if update.effective_user is None or update.effective_message is None:
            return
        if update.effective_message.text is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            # Silently ignore non-allowed users in groups to avoid spam
            if in_group:
                return
            await update.effective_message.reply_text("Not authorized.")
            return

        # In group chats, route replies to the group; in private chats, DM the user
        if in_group:
            assert chat is not None
            platform_user = str(chat.id)
            sender_platform_user = str(user_id)
            session_title = chat.title
        else:
            platform_user = str(user_id)
            sender_platform_user = None
            session_title = None

        # Check for pending workflow interactive responses
        from hestia.workflows.response_store import DEFAULT_RESPONSE_STORE

        pending_request_id = DEFAULT_RESPONSE_STORE.find_pending(
            "telegram", platform_user
        )
        if pending_request_id is not None:
            resolved = DEFAULT_RESPONSE_STORE.resolve(
                pending_request_id, update.effective_message.text
            )
            if resolved:
                # Don't route workflow replies to the orchestrator
                return

        if self._on_message is not None:
            await self._on_message(
                self.name,
                platform_user,
                update.effective_message.text,
                sender_platform_user,
                session_title,
            )

    async def _handle_voice_message(self, update: Update, context: Any) -> None:
        """Handle incoming voice messages: STT → orchestrator → TTS → voice reply."""
        if not self._config.voice_messages:
            logger.debug("Voice message ignored (telegram.voice_messages=False)")
            return

        if update.effective_user is None or update.effective_message is None:
            return
        if update.effective_message.voice is None:
            return

        user_id = update.effective_user.id
        username = update.effective_user.username or str(user_id)
        message = update.effective_message
        chat = update.effective_chat
        in_group = chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP)

        if not self._is_allowed(user_id, username):
            if in_group:
                return
            await message.reply_text("Not authorized.")
            return

        if (
            self._session_store is None
            or self._handoff_service is None
            or self._orchestrator is None
            or self._voice_config is None
        ):
            logger.warning("Voice deps not injected; cannot process voice message")
            await message.reply_text("Voice processing is not configured.")
            return

        assert message.voice is not None
        # BUG-063: in groups the session lives on the chat id; typing must
        # target the chat the user spoke in, not their private DM.
        _user_key = str(chat.id if (in_group and chat is not None) else user_id)
        await self.set_typing(_user_key, True)

        try:
            # 1. Download the .ogg file
            ogg_path: str | None = None
            try:
                voice_file = await message.voice.get_file(read_timeout=60.0)
                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg:
                    await voice_file.download_to_drive(
                        ogg.name, read_timeout=60.0, write_timeout=60.0
                    )
                    ogg_path = ogg.name
            except Exception as e:  # noqa: BLE001 — voice download boundary
                logger.warning("Failed to download voice message: %s", e)
                if ogg_path is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(ogg_path)
                await message.reply_text("Sorry, I couldn't download that voice message.")
                return

            # 2. Convert .ogg/opus to PCM 16kHz mono via ffmpeg
            try:
                pcm_bytes = await self._ogg_to_pcm(ogg_path, sample_rate=16000)
            except Exception as e:  # noqa: BLE001 — audio conversion boundary
                logger.warning("Failed to convert voice message to PCM: %s", e)
                await message.reply_text("Sorry, I couldn't process that audio format.")
                return
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(ogg_path)

            # Guard against sub-word Whisper hallucinations on accidental tap-and-release
            _min_mono16_bytes = 8_000  # ~0.25 s at 16 kHz mono 16-bit
            if len(pcm_bytes) < _min_mono16_bytes:
                await message.reply_text("I didn't catch that — could you speak a little longer?")
                return

            # 3. Transcribe
            try:
                pipeline = await get_voice_pipeline(self._voice_config)
                transcript = await pipeline.transcribe(pcm_bytes, sample_rate=16000)
            except Exception as e:  # noqa: BLE001 — STT boundary
                logger.warning("STT failed for voice message: %s", e)
                await message.reply_text("Sorry, I couldn't understand that audio.")
                return

            if not transcript.strip():
                await message.reply_text("Sorry, I didn't catch anything in that message.")
                return

            # 4. Feed to orchestrator as a normal text turn
            # In groups, use chat ID as session key so replies stay in the group
            if in_group:
                assert chat is not None
                platform_user = str(chat.id)
                _sender_platform_user = str(user_id)
                session_title = chat.title
            else:
                platform_user = str(user_id)
                _sender_platform_user = None
                session_title = None
            session = await self._handoff_service.get_or_create_session_with_handoff(
                "telegram", platform_user, title=session_title
            )
            user_message = HestiaMessage(role="user", content=transcript)

            async def respond_voice(response_text: str) -> None:
                """Synthesize the response and send it as a voice message."""
                # 5. Synthesize → assemble .ogg/opus
                audio_chunks: list[bytes] = []
                try:
                    async for chunk in pipeline.synthesize(response_text):
                        audio_chunks.append(chunk)
                except Exception as synth_err:  # noqa: BLE001 — TTS boundary
                    logger.warning("TTS failed for voice reply: %s", synth_err)
                    _prefix = "(Voice synthesis failed; sending text instead)"
                    _text = f"{_prefix}\n\n{_md_to_tg_html(response_text)}"
                    await message.reply_text(_text, parse_mode="HTML")
                    return

                try:
                    full_audio_ogg = await self._pcm_chunks_to_ogg_opus(audio_chunks)
                except Exception as enc_err:  # noqa: BLE001 — audio encoding boundary
                    logger.warning("OGG encoding failed for voice reply: %s", enc_err)
                    _prefix = "(Voice encoding failed; sending text instead)"
                    _text = f"{_prefix}\n\n{_md_to_tg_html(response_text)}"
                    await message.reply_text(_text, parse_mode="HTML")
                    return

                # 6. Telegram voice note limit handling (1 MB)
                if len(full_audio_ogg) > 1_000_000:
                    total_pcm = b"".join(audio_chunks)
                    duration_seconds = len(total_pcm) / (self._tts_sample_rate() * 2)
                    try:
                        truncated_ogg = await self._truncate_ogg_to_size(
                            full_audio_ogg, 1_000_000, duration_seconds
                        )
                    except Exception as trunc_err:  # noqa: BLE001 — best-effort truncation
                        logger.warning("OGG truncation failed: %s", trunc_err)
                        truncated_ogg = full_audio_ogg
                    await message.reply_voice(voice=io.BytesIO(truncated_ogg))
                    await message.reply_text(
                        "(Voice reply truncated to fit Telegram's 1MB limit. "
                        "Full text:)\n\n" + _md_to_tg_html(response_text),
                        parse_mode="HTML",
                    )
                else:
                    await message.reply_voice(voice=io.BytesIO(full_audio_ogg))

            # BUG-014: bind the runner's identity ContextVars so gated tools
            # can confirm against a real requester (previously every
            # confirmation auto-denied), and attribute the turn to Telegram.
            user_token = (
                self._user_context_var.set(platform_user)
                if self._user_context_var is not None
                else None
            )
            requester_token = (
                self._requester_context_var.set(_sender_platform_user or platform_user)
                if self._requester_context_var is not None
                else None
            )
            try:
                await self._orchestrator.process_turn(
                    session=session,
                    user_message=user_message,
                    respond_callback=respond_voice,
                    system_prompt=self._system_prompt,
                    platform=self,
                    platform_user=platform_user,
                    voice_reply=True,
                    channel=Channel.TELEGRAM,
                )
            except Exception as e:  # noqa: BLE001 — turn boundary
                logger.exception("Turn failed for voice message from %s", user_id)
                await message.reply_text(sanitize_user_error(e))
            finally:
                if requester_token is not None and self._requester_context_var is not None:
                    self._requester_context_var.reset(requester_token)
                if user_token is not None and self._user_context_var is not None:
                    self._user_context_var.reset(user_token)
        finally:
            await self.set_typing(_user_key, False)

    async def _handle_callback_query(self, update: Update, context: Any) -> None:
        """Handle inline-keyboard button presses for confirmations and workflow responses."""
        if update.callback_query is None or update.callback_query.data is None:
            return

        data = update.callback_query.data

        # Workflow interactive responses
        if data.startswith("workflow:"):
            parts = data.split(":", 2)
            if len(parts) == 3:
                _prefix, request_id, response = parts
                from hestia.workflows.response_store import DEFAULT_RESPONSE_STORE

                resolved = DEFAULT_RESPONSE_STORE.resolve(request_id, response)
                if resolved:
                    await update.callback_query.answer(f"Selected: {response}")
                    # Update the original message to remove the keyboard
                    msg = update.callback_query.message
                    if msg is not None:
                        try:
                            original_text = getattr(msg, "text", None) or ""
                            await update.callback_query.edit_message_text(
                                text=f"{original_text}\n\n✅ {response}",
                                parse_mode="HTML",
                            )
                        except TelegramError as e:
                            logger.debug("Failed to update workflow message: %s", e)
                else:
                    await update.callback_query.answer("This prompt has expired.")
            return

        if not data.startswith("confirm:"):
            return

        parts = data.split(":")
        if len(parts) != 3:
            await update.callback_query.answer("Invalid confirmation.")
            return

        _prefix, request_id, answer = parts
        approved = answer == "yes"

        approver = None
        if update.callback_query.from_user is not None:
            approver = str(update.callback_query.from_user.id)

        resolved = self._confirmation_store.resolve(request_id, approved, approver)

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

    # ------------------------------------------------------------------
    # FFmpeg helpers
    # ------------------------------------------------------------------

    async def _ogg_to_pcm(self, ogg_path: str, sample_rate: int = 16000) -> bytes:
        """Convert an OGG/Opus file to raw PCM16 mono bytes."""
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            ogg_path,
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg ogg→pcm failed: {stderr.decode().strip()}")
        return stdout

    async def _pcm_chunks_to_ogg_opus(self, chunks: list[bytes]) -> bytes:
        """Merge PCM16 chunks and encode to OGG/Opus via ffmpeg."""
        pcm = b"".join(chunks)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            str(self._tts_sample_rate()),
            "-ac",
            "1",
            "-i",
            "-",
            "-c:a",
            "libopus",
            "-b:a",
            "24k",
            "-f",
            "ogg",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=pcm)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg pcm→ogg failed: {stderr.decode().strip()}")
        return stdout

    async def _truncate_ogg_to_size(
        self, ogg_bytes: bytes, max_size: int, original_duration_seconds: float
    ) -> bytes:
        """Iteratively shorten an OGG/Opus file until it fits within ``max_size`` bytes."""
        best_result = ogg_bytes
        for factor in (0.85, 0.7, 0.55, 0.4, 0.25):
            target_duration = original_duration_seconds * factor
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "-",
                "-t",
                str(target_duration),
                "-c:a",
                "libopus",
                "-b:a",
                "24k",
                "-f",
                "ogg",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(input=ogg_bytes)
            if proc.returncode == 0:
                best_result = stdout
                if len(stdout) <= max_size:
                    return stdout
        logger.warning(
            "Could not truncate voice reply to %d bytes; returning best attempt (%d bytes)",
            max_size,
            len(best_result),
        )
        return best_result
