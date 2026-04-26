"""Telegram platform adapter."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import tempfile
import time
from typing import TYPE_CHECKING, Any

from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from hestia.config import TelegramConfig
from hestia.core.types import Message as HestiaMessage
from hestia.platforms.allowlist import (
    match_allowlist,
    validate_telegram_user_id,
    validate_telegram_username,
)
from hestia.platforms.base import IncomingMessageCallback, Platform
from hestia.platforms.confirmation import ConfirmationStore, render_args_for_human_review
from hestia.voice.pipeline import get_voice_pipeline

if TYPE_CHECKING:
    from hestia.config import VoiceConfig
    from hestia.orchestrator.engine import Orchestrator
    from hestia.persistence.sessions import SessionStore


def _md_to_tg_html(text: str) -> str:
    """Convert basic Markdown to Telegram HTML parse_mode.

    Handles **bold**, *italic*, `inline code`, and ```code blocks```.
    Escapes HTML entities to avoid parse errors.
    """
    import re

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
        # Skip if it looks like it was meant to be bold (contains * or already has tags)
        if "*" in inner or "<b>" in inner or "</b>" in inner:
            return m.group(0)
        return f"<i>{inner}</i>"

    text = re.sub(r"\*([^*\n]+)\*", _italic_repl, text)

    return text


logger = logging.getLogger(__name__)

# Piper outputs PCM16 mono at 22050 Hz for the default en_US-amy-medium voice.
_TTS_SAMPLE_RATE = 22050


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

        # Background tasks that keep the typing indicator alive (refreshed every 4s).
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}

        # Voice deps are injected by run_platform when voice is enabled.
        self._orchestrator: Orchestrator | None = None
        self._session_store: SessionStore | None = None
        self._system_prompt: str = ""
        self._voice_config: VoiceConfig | None = None

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
        system_prompt: str,
        voice_config: VoiceConfig,
    ) -> None:
        """Inject orchestrator and session store for voice message handling.

        Called by run_platform after the orchestrator is built.
        """
        self._orchestrator = orchestrator
        self._session_store = session_store
        self._system_prompt = system_prompt
        self._voice_config = voice_config

    async def start(self, on_message: IncomingMessageCallback) -> None:
        """Start polling for Telegram messages."""
        self._on_message = on_message

        self._app = Application.builder().token(self._config.bot_token).http_version("1.1").build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
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

    async def send_message(self, user: str, text: str) -> str:
        """Send a message to a Telegram chat. Returns message ID."""
        if self._app is None:
            raise RuntimeError("Telegram adapter not started")

        chat_id = int(user)
        msg = await self._app.bot.send_message(
            chat_id=chat_id,
            text=_md_to_tg_html(text),
            parse_mode="HTML",
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
                text=_md_to_tg_html(text),
                parse_mode="HTML",
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

        return (
            match_allowlist(allowed, str(user_id), case_sensitive=True)
            or (username is not None
                and match_allowlist(allowed, username, case_sensitive=False))
        )

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
        else:
            platform_user = str(user_id)

        if self._on_message is not None:
            await self._on_message(
                self.name,
                platform_user,
                update.effective_message.text,
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

        if self._session_store is None or self._orchestrator is None or self._voice_config is None:
            logger.warning("Voice deps not injected; cannot process voice message")
            await message.reply_text("Voice processing is not configured.")
            return

        assert message.voice is not None

        # 1. Download the .ogg file
        try:
            voice_file = await message.voice.get_file()
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg:
                await voice_file.download_to_drive(ogg.name)
                ogg_path = ogg.name
        except Exception as e:
            logger.warning("Failed to download voice message: %s", e)
            await message.reply_text("Sorry, I couldn't download that voice message.")
            return

        # 2. Convert .ogg/opus to PCM 16kHz mono via ffmpeg
        try:
            pcm_bytes = await self._ogg_to_pcm(ogg_path, sample_rate=16000)
        except Exception as e:
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
        except Exception as e:
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
        else:
            platform_user = str(user_id)
        session = await self._session_store.get_or_create_session("telegram", platform_user)
        user_message = HestiaMessage(role="user", content=transcript)

        async def respond_voice(response_text: str) -> None:
            """Synthesize the response and send it as a voice message."""
            # 5. Synthesize → assemble .ogg/opus
            audio_chunks: list[bytes] = []
            try:
                async for chunk in pipeline.synthesize(response_text):
                    audio_chunks.append(chunk)
            except Exception as synth_err:
                logger.warning("TTS failed for voice reply: %s", synth_err)
                _prefix = "(Voice synthesis failed; sending text instead)"
                _text = f"{_prefix}\n\n{_md_to_tg_html(response_text)}"
                await message.reply_text(_text, parse_mode="HTML")
                return

            try:
                full_audio_ogg = await self._pcm_chunks_to_ogg_opus(audio_chunks)
            except Exception as enc_err:
                logger.warning("OGG encoding failed for voice reply: %s", enc_err)
                _prefix = "(Voice encoding failed; sending text instead)"
                _text = f"{_prefix}\n\n{_md_to_tg_html(response_text)}"
                await message.reply_text(_text, parse_mode="HTML")
                return

            # 6. Telegram voice note limit handling (1 MB)
            if len(full_audio_ogg) > 1_000_000:
                total_pcm = b"".join(audio_chunks)
                duration_seconds = len(total_pcm) / (_TTS_SAMPLE_RATE * 2)
                try:
                    truncated_ogg = await self._truncate_ogg_to_size(
                        full_audio_ogg, 1_000_000, duration_seconds
                    )
                except Exception as trunc_err:
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

        try:
            await self._orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=respond_voice,
                system_prompt=self._system_prompt,
                platform=self,
                platform_user=platform_user,
                voice_reply=True,
            )
        except Exception as e:
            logger.exception("Turn failed for voice message from %s", user_id)
            await message.reply_text(f"Turn failed: {e}")

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
            str(_TTS_SAMPLE_RATE),
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
