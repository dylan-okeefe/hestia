"""Discord voice-channel listener (Phase B sub-scope A).

Joins a configured voice channel, records decoded PCM from speakers, and logs
STT transcripts. Requires ``hestia[voice]`` (py-cord + faster-whisper + piper).
"""

from __future__ import annotations

import asyncio
import audioop
import logging
import sys
import threading
from typing import TYPE_CHECKING, Any

import click

from hestia.config import validate_discord_voice_for_run
from hestia.errors import MissingExtraError
from hestia.voice.pipeline import get_voice_pipeline

if TYPE_CHECKING:
    from hestia.app import CliAppContext
    from hestia.config import HestiaConfig

logger = logging.getLogger(__name__)

try:
    import discord
    from discord import sinks
    from discord.ext import commands
except ImportError:  # pragma: no cover - exercised when extra missing
    discord = None  # type: ignore[assignment]
    sinks = None  # type: ignore[assignment]
    commands = None  # type: ignore[assignment]

# View, Send, Read history, Connect, Speak, Use voice activity (Discord docs bitfield).
DISCORD_VOICE_INVITE_PERMISSIONS = (
    1024 + 2048 + 65536 + 1048576 + 2097152 + 33554432
)


def discord_voice_invite_url(application_id: str) -> str:
    """Return the standard bot invite URL for Phase B channel permissions."""
    aid = application_id.strip()
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={aid}&permissions={DISCORD_VOICE_INVITE_PERMISSIONS}&scope=bot"
    )


def _transcription_sink_class() -> type:
    """Build Sink subclass only when py-cord is importable."""
    assert sinks is not None

    class TranscriptionSink(sinks.Sink):
        """Buffers stereo 48kHz PCM per user; flushes after quiet or size cap."""

        _QUIET_SEC = 2.5
        _MIN_MONO16_BYTES = 32_000  # ~1s at 16 kHz mono int16
        _MAX_STEREO_BYTES = 960_000  # ~5s stereo 48kHz before forced flush

        def __init__(
            self,
            loop: asyncio.AbstractEventLoop,
            allowed: tuple[int, ...],
            transcribe_user: Any,
        ) -> None:
            super().__init__(filters={"users": [], "time": 0, "max_size": 0})
            self._loop = loop
            self._allowed = allowed
            self._buffers: dict[int, bytearray] = {}
            self._lock = threading.Lock()
            self._timers: dict[int, threading.Timer] = {}
            self._transcribe_user = transcribe_user

        def _cancel_timer(self, uid: int) -> None:
            t = self._timers.pop(uid, None)
            if t is not None:
                t.cancel()

        def _snapshot_stereo(self, uid: int) -> bytes:
            with self._lock:
                buf = self._buffers.get(uid)
                if not buf:
                    return b""
                out = bytes(buf)
                buf.clear()
            return out

        def _flush_stereo(self, uid: int, pcm_stereo: bytes) -> None:
            if not pcm_stereo:
                return
            mono = audioop.tomono(pcm_stereo, 2, 0.5, 0.5)
            mono_16k, _ = audioop.ratecv(mono, 2, 1, 48000, 16000, None)
            if len(mono_16k) < self._MIN_MONO16_BYTES:
                return
            asyncio.run_coroutine_threadsafe(self._transcribe_user(uid, mono_16k), self._loop)

        def _schedule_flush(self, uid: int) -> None:
            self._cancel_timer(uid)

            def fire() -> None:
                self._timers.pop(uid, None)
                pcm = self._snapshot_stereo(uid)
                self._flush_stereo(uid, pcm)

            timer = threading.Timer(self._QUIET_SEC, fire)
            self._timers[uid] = timer
            timer.daemon = True
            timer.start()

        @sinks.Filters.container  # type: ignore[attr-defined]
        def write(self, data: bytes, user: int) -> None:
            if self._allowed and user not in self._allowed:
                return
            flush_prefix = b""
            with self._lock:
                buf = self._buffers.setdefault(user, bytearray())
                buf.extend(data)
                if len(buf) > self._MAX_STEREO_BYTES:
                    take = len(buf) - self._MAX_STEREO_BYTES + 192_000
                    flush_prefix = bytes(buf[:take])
                    del buf[:take]
            if flush_prefix:
                self._flush_stereo(user, flush_prefix)
            self._schedule_flush(user)

        def cleanup(self) -> None:
            self.finished = True
            for _uid, timer in list(self._timers.items()):
                timer.cancel()
            self._timers.clear()
            with self._lock:
                users = list(self._buffers.keys())
            for uid in users:
                pcm = self._snapshot_stereo(uid)
                self._flush_stereo(uid, pcm)

    return TranscriptionSink


async def run_discord_voice(app: CliAppContext, config: HestiaConfig) -> None:
    """Connect to Discord voice and log per-user transcripts (Phase B sub-scope A)."""
    if discord is None or commands is None or sinks is None:
        click.echo(
            "Error: py-cord is not installed. Install with: uv pip install 'hestia[voice]'",
            err=True,
        )
        sys.exit(1)

    dv = config.discord_voice
    if not dv.enabled:
        click.echo(
            "Error: discord_voice.enabled is False. Set HESTIA_DISCORD_VOICE_ENABLED=1 "
            "or enable in config.",
            err=True,
        )
        sys.exit(1)

    try:
        validate_discord_voice_for_run(dv)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    await app.bootstrap_db()

    sink_cls = _transcription_sink_class()

    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    sem = asyncio.Semaphore(2)

    async def transcribe_user(user_id: int, pcm_mono16: bytes) -> None:
        async with sem:
            try:
                pipeline = await get_voice_pipeline(config.voice)
            except MissingExtraError as exc:
                logger.error("Discord voice: voice pipeline unavailable: %s", exc)
                return
            try:
                text = await pipeline.transcribe(pcm_mono16, sample_rate=16000)
            except Exception:
                logger.exception("Discord voice: STT failed for user %s", user_id)
                return
            logger.info("discord voice user=%s transcript=%r", user_id, text or "")

    @bot.event
    async def on_ready() -> None:
        if getattr(bot, "_hestia_voice_joined", False):
            return
        bot._hestia_voice_joined = True
        assert bot.user is not None
        logger.info("Discord voice logged in as %s (%s)", bot.user, bot.user.id)
        guild = bot.get_guild(dv.guild_id)
        if guild is None:
            logger.error(
                "Guild id %s not visible to bot (missing intent or wrong id).",
                dv.guild_id,
            )
            await bot.close()
            return
        ch = guild.get_channel(dv.voice_channel_id)
        if not isinstance(ch, discord.VoiceChannel):
            logger.error("Channel %s is not a voice channel.", dv.voice_channel_id)
            await bot.close()
            return
        try:
            vc = await ch.connect()
        except Exception:
            logger.exception("Failed to connect to voice channel %s", dv.voice_channel_id)
            await bot.close()
            return

        loop = asyncio.get_running_loop()
        sink = sink_cls(loop, dv.allowed_speaker_ids, transcribe_user)

        async def _finished(_sink: Any, *_a: Any, **_kw: Any) -> None:
            logger.info("Discord voice recording finished.")

        vc.start_recording(sink, _finished)
        click.echo(
            f"Discord voice connected to #{ch.name} in {guild.name}. "
            "Speak to see transcripts in logs (Ctrl-C to stop)."
        )

        if dv.text_channel_id:
            tch = guild.get_channel(dv.text_channel_id)
            if isinstance(tch, discord.TextChannel):
                await tch.send(
                    "Hestia voice: connected and listening (transcripts go to server logs)."
                )

    token = dv.bot_token.strip()
    try:
        await bot.start(token)
    finally:
        await bot.close()


def print_discord_voice_setup_instructions(application_id: str | None) -> None:
    """Print invite URL and env hints for operators."""
    click.echo("Discord voice (Phase B) setup:\n")
    click.echo("1. In the Discord Developer Portal, open your application and copy")
    click.echo("   the **Application ID** (same as OAuth2 client id).\n")
    if application_id and application_id.strip().isdigit():
        url = discord_voice_invite_url(application_id.strip())
        click.echo("2. Open this URL in a browser while logged into Discord, pick your server,")
        click.echo("   then authorize:\n")
        click.echo(f"   {url}\n")
    else:
        click.echo(
            "2. Build an invite URL (replace YOUR_APPLICATION_ID):\n"
            f"   https://discord.com/oauth2/authorize"
            f"?client_id=YOUR_APPLICATION_ID&permissions={DISCORD_VOICE_INVITE_PERMISSIONS}"
            "&scope=bot\n"
        )
    click.echo("3. Set privileged intents on the Bot tab if you need them (e.g. Message")
    click.echo("   Content for reading text). Ensure the bot role can Connect/Speak in")
    click.echo("   the target voice channel.\n")
    click.echo("4. Put secrets in the environment (never commit):\n")
    click.echo("     HESTIA_DISCORD_TOKEN\n")
    click.echo("     HESTIA_DISCORD_GUILD_ID\n")
    click.echo("     HESTIA_DISCORD_VOICE_CHANNEL_ID\n")
    click.echo("     optional: HESTIA_DISCORD_TEXT_CHANNEL_ID, HESTIA_DISCORD_ALLOWED_USER_IDS\n")
    click.echo("     HESTIA_DISCORD_VOICE_ENABLED=1\n")
    click.echo("5. Run:  hestia --config yourconfig.py discord-voice\n")
