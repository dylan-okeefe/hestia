"""Discord voice-channel listener (Phase B sub-scopes A–C).

Joins a configured voice channel, records decoded PCM from speakers,
transcribes via faster-whisper, detects turns via heuristic turn detector,
dispatches completed turns through the orchestrator, and streams TTS
responses back into the voice channel.

Requires ``hestia[voice]`` (py-cord + faster-whisper + piper).
"""

from __future__ import annotations

import asyncio
import audioop
import logging
import queue
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

import click

from hestia.config import validate_discord_voice_for_run
from hestia.core.types import Message
from hestia.errors import MissingExtraError
from hestia.voice.pipeline import get_voice_pipeline
from hestia.voice.turn_detector import HeuristicTurnDetector, TurnDetectorConfig

if TYPE_CHECKING:
    from hestia.app import CliAppContext
    from hestia.config import HestiaConfig

logger = logging.getLogger(__name__)

try:
    import discord
    from discord import sinks
    from discord.ext import commands
    from discord.opus import Encoder as OpusEncoder
except ImportError:  # pragma: no cover - exercised when extra missing
    discord = None  # type: ignore[assignment]
    sinks = None  # type: ignore[assignment]
    commands = None  # type: ignore[assignment]
    OpusEncoder = None  # type: ignore[assignment,misc]

# View, Send, Read history, Connect, Speak, Use voice activity (Discord docs bitfield).
DISCORD_VOICE_INVITE_PERMISSIONS = (
    1024 + 2048 + 65536 + 1048576 + 2097152 + 33554432
)

# Piper typically outputs 22050 Hz mono PCM16.
_PIPER_SAMPLE_RATE = 22050


def discord_voice_invite_url(application_id: str) -> str:
    """Return the standard bot invite URL for Phase B channel permissions."""
    aid = application_id.strip()
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={aid}&permissions={DISCORD_VOICE_INVITE_PERMISSIONS}&scope=bot"
    )


class _QueueAudioSource(discord.AudioSource):
    """Reads 48 kHz stereo PCM16 from a thread-safe queue for py-cord playback."""

    def __init__(self) -> None:
        self._q: queue.Queue[bytes] = queue.Queue()
        self._finished = False
        self._buffer = b""
        self._frame_size: int = OpusEncoder.FRAME_SIZE if OpusEncoder is not None else 3840

    def write(self, data: bytes) -> None:
        """Feed PCM data from the async side."""
        self._q.put(data)

    def finish(self) -> None:
        """Signal end of stream."""
        self._finished = True

    def read(self) -> bytes:
        """Called by py-cord audio player thread — must return 20 ms frame."""
        while len(self._buffer) < self._frame_size and not self._finished:
            try:
                chunk = self._q.get(timeout=0.05)
                self._buffer += chunk
            except queue.Empty:
                continue
        if len(self._buffer) >= self._frame_size:
            frame = self._buffer[:self._frame_size]
            self._buffer = self._buffer[self._frame_size:]
            return frame
        return b""

    def cleanup(self) -> None:
        self._finished = True
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break


def _resample_for_discord(pcm_mono: bytes, src_rate: int) -> bytes:
    """Convert mono PCM16 at *src_rate* to stereo PCM16 at 48 kHz."""
    if src_rate != 48000:
        pcm_mono, _ = audioop.ratecv(pcm_mono, 2, 1, src_rate, 48000, None)
    stereo = audioop.tostereo(pcm_mono, 2, 0.5, 0.5)
    return stereo


class SpeakerSession:
    """Conversation state machine for a single Discord speaker."""

    def __init__(
        self,
        user_id: int,
        app: CliAppContext,
        config: HestiaConfig,
        voice_client: Any,
    ) -> None:
        self.user_id = user_id
        self.app = app
        self.config = config
        self.voice_client = voice_client
        self.turn_detector = HeuristicTurnDetector(
            TurnDetectorConfig(
                smart_turn_threshold=config.discord_voice.smart_turn_threshold,
                fast_silence_ms=config.discord_voice.fast_silence_ms,
                patient_silence_ms=config.discord_voice.patient_silence_ms,
                safety_timeout_ms=config.discord_voice.safety_timeout_ms,
                filler_words=config.discord_voice.filler_words,
                end_of_turn_keywords=config.discord_voice.end_of_turn_keywords,
            )
        )
        self._accumulated_audio = b""
        self._accumulated_text = ""
        self._last_audio_time = time.monotonic()
        self._patience_task: asyncio.Task[None] | None = None
        self._tts_lock = asyncio.Lock()
        self._current_source: _QueueAudioSource | None = None
        self._sem = asyncio.Semaphore(2)
        self._confirm_callback: Any | None = None

    def on_audio_chunk(self, pcm_mono16: bytes) -> None:
        """Called from the sink flush thread — queue audio for processing."""
        self._accumulated_audio += pcm_mono16
        self._last_audio_time = time.monotonic()
        # Cancel any pending patience commit — user is still speaking
        if self._patience_task is not None and not self._patience_task.done():
            self._patience_task.cancel()
            self._patience_task = None

    def set_confirm_callback(self, callback: Any | None) -> None:
        """Register a confirmation callback that may intercept transcripts."""
        self._confirm_callback = callback

    async def check_turn(self, silence_ms: int) -> None:
        """Evaluate whether the current accumulated audio forms a complete turn."""
        if not self._accumulated_audio:
            return

        async with self._sem:
            try:
                pipeline = await get_voice_pipeline(self.config.voice)
            except MissingExtraError as exc:
                logger.error("Voice pipeline unavailable: %s", exc)
                return

            try:
                text = await pipeline.transcribe(
                    self._accumulated_audio, sample_rate=16000
                )
            except Exception:
                logger.exception("STT failed for user %s", self.user_id)
                return

        if not text:
            return

        # If a confirmation callback is waiting, route the transcript to it
        # instead of treating it as a new turn.
        if self._confirm_callback is not None:
            self._confirm_callback.on_transcript(text)
            self._accumulated_audio = b""
            return

        self._accumulated_text = text
        should_commit, confidence = self.turn_detector.should_commit(text, int(silence_ms))
        logger.debug(
            "user=%s silence=%.0fms text=%r commit=%s conf=%.2f",
            self.user_id,
            silence_ms,
            text,
            should_commit,
            confidence,
        )

        if should_commit:
            await self._commit_turn()
        else:
            # Schedule a patience commit
            remaining = max(
                500,
                self.config.discord_voice.patient_silence_ms - silence_ms,
            )
            self._patience_task = asyncio.create_task(
                self._patience_commit(remaining)
            )

    async def _patience_commit(self, delay_ms: int) -> None:
        """Force commit after *delay_ms* if no new audio arrives."""
        try:
            await asyncio.sleep(delay_ms / 1000.0)
            silence_ms = (time.monotonic() - self._last_audio_time) * 1000
            # Re-check with updated silence
            should_commit, _ = self.turn_detector.should_commit(
                self._accumulated_text, int(silence_ms)
            )
            if should_commit or self._accumulated_text:
                await self._commit_turn()
        except asyncio.CancelledError:
            pass

    async def _commit_turn(self) -> None:
        """Process the accumulated transcript through the orchestrator."""
        transcript = self._accumulated_text
        self._accumulated_text = ""
        self._accumulated_audio = b""
        if self._patience_task is not None:
            self._patience_task.cancel()
            self._patience_task = None

        if not transcript.strip():
            return

        logger.info(
            "discord voice user=%s turn_committed transcript=%r",
            self.user_id,
            transcript,
        )

        # Resolve session
        try:
            session = await self.app.session_store.get_or_create_session(
                "discord", str(self.user_id)
            )
        except Exception:
            logger.exception("Failed to get session for discord user %s", self.user_id)
            return

        user_message = Message(role="user", content=transcript)
        response_parts: list[str] = []

        async def _respond_callback(text: str) -> None:
            response_parts.append(text)

        from hestia.platforms.voice_confirm import make_voice_confirm_callback

        confirm_cb = make_voice_confirm_callback(self)
        self.set_confirm_callback(confirm_cb)
        self.app.set_confirm_callback(confirm_cb)
        orchestrator = self.app.make_orchestrator()
        try:
            await orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=_respond_callback,
                system_prompt=self.config.system_prompt or "You are a helpful assistant.",
                platform=None,
                platform_user=str(self.user_id),
            )
        except Exception:
            logger.exception("Orchestrator turn failed for user %s", self.user_id)
            return
        finally:
            self.set_confirm_callback(None)
            self.app.set_confirm_callback(None)

        full_response = "".join(response_parts)
        if not full_response.strip():
            return

        await self._speak(full_response)

    async def _speak(self, text: str) -> None:
        """Synthesize *text* and play it into the voice channel."""
        async with self._tts_lock:
            try:
                pipeline = await get_voice_pipeline(self.config.voice)
            except MissingExtraError as exc:
                logger.error("TTS unavailable: %s", exc)
                return

            source = _QueueAudioSource()
            self._current_source = source

            async def _play() -> None:
                if self.voice_client is not None:
                    self.voice_client.play(source)

            # Start playback immediately so the queue can be fed
            await _play()

            try:
                async for chunk in pipeline.synthesize(text):
                    # Piper chunk is PCM16 mono at ~22050 Hz
                    discord_pcm = _resample_for_discord(chunk, _PIPER_SAMPLE_RATE)
                    source.write(discord_pcm)
            except Exception:
                logger.exception("TTS synthesis failed for user %s", self.user_id)
            finally:
                source.finish()
                # Wait briefly for playback to drain
                await asyncio.sleep(0.5)
                if self.voice_client is not None and self.voice_client.is_playing():
                    self.voice_client.stop()
                self._current_source = None

    def barge_in(self) -> None:
        """Stop current TTS playback (called when new speech detected during speak)."""
        if self.voice_client is not None and self.voice_client.is_playing():
            self.voice_client.stop()
        if self._current_source is not None:
            self._current_source.finish()
            self._current_source = None


def _transcription_sink_class(
    loop: asyncio.AbstractEventLoop,
    config: HestiaConfig,
    app: CliAppContext,
    voice_client: Any,
    sessions: dict[int, SpeakerSession],
) -> type:
    """Build Sink subclass only when py-cord is importable."""
    assert sinks is not None

    fast_silence_sec = config.discord_voice.fast_silence_ms / 1000.0

    class TranscriptionSink(sinks.Sink):
        """Buffers stereo 48 kHz PCM per user; flushes after quiet."""

        _MIN_MONO16_BYTES = 32_000  # ~1 s at 16 kHz mono int16
        _MAX_STEREO_BYTES = 960_000  # ~5 s stereo 48 kHz before forced flush

        def __init__(self) -> None:
            super().__init__(filters={"users": [], "time": 0, "max_size": 0})  # type: ignore[no-untyped-call]
            self._buffers: dict[int, bytearray] = {}
            self._lock = threading.Lock()
            self._timers: dict[int, threading.Timer] = {}
            self._allowed = config.discord_voice.allowed_speaker_ids

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

        def _flush(self, uid: int, pcm_stereo: bytes) -> None:
            if not pcm_stereo:
                return
            mono = audioop.tomono(pcm_stereo, 2, 0.5, 0.5)
            mono_16k, _ = audioop.ratecv(mono, 2, 1, 48000, 16000, None)
            if len(mono_16k) < self._MIN_MONO16_BYTES:
                return

            # Barge-in: if this user already has a session and TTS is playing,
            # stop it so the new audio starts a fresh turn.
            session = sessions.get(uid)
            if session is not None:
                session.barge_in()
                session.on_audio_chunk(mono_16k)
            else:
                if self._allowed and uid not in self._allowed:
                    return
                new_session = SpeakerSession(uid, app, config, voice_client)
                sessions[uid] = new_session
                new_session.on_audio_chunk(mono_16k)

            # Schedule turn check after fast silence
            asyncio.run_coroutine_threadsafe(
                sessions[uid].check_turn(config.discord_voice.fast_silence_ms),
                loop,
            )

        def _schedule_flush(self, uid: int) -> None:
            self._cancel_timer(uid)

            def fire() -> None:
                self._timers.pop(uid, None)
                pcm = self._snapshot_stereo(uid)
                self._flush(uid, pcm)

            timer = threading.Timer(fast_silence_sec, fire)
            self._timers[uid] = timer
            timer.daemon = True
            timer.start()

        @sinks.Filters.container  # type: ignore
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
                self._flush(user, flush_prefix)
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
                self._flush(uid, pcm)

    return TranscriptionSink


async def run_discord_voice(app: CliAppContext, config: HestiaConfig) -> None:
    """Connect to Discord voice and run the full conversation loop (sub-scopes A–C)."""
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

    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    sessions: dict[int, SpeakerSession] = {}
    voice_client: Any = None

    @bot.event
    async def on_ready() -> None:
        nonlocal voice_client
        if hasattr(bot, "_hestia_voice_joined") and bot._hestia_voice_joined:
            return
        bot._hestia_voice_joined = True  # type: ignore[attr-defined]
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
            voice_client = await ch.connect()
        except Exception:
            logger.exception("Failed to connect to voice channel %s", dv.voice_channel_id)
            await bot.close()
            return

        loop = asyncio.get_running_loop()
        sink_cls = _transcription_sink_class(loop, config, app, voice_client, sessions)
        sink = sink_cls()

        async def _finished(_sink: Any, *_a: Any, **_kw: Any) -> None:
            logger.info("Discord voice recording finished.")

        voice_client.start_recording(sink, _finished)
        click.echo(
            f"Discord voice connected to #{ch.name} in {guild.name}. "
            "Speak to interact (Ctrl-C to stop)."
        )

        if dv.text_channel_id:
            tch = guild.get_channel(dv.text_channel_id)
            if isinstance(tch, discord.TextChannel):
                await tch.send(
                    "Hestia voice: connected and listening."
                )

    @bot.event
    async def on_voice_state_update(
        member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Clean up speaker sessions when users leave the voice channel."""
        if bot.user is not None and member.id == bot.user.id:
            return
        if before.channel is not None and after.channel is None:
            session = sessions.pop(member.id, None)
            if session is not None:
                logger.info("User %s left voice channel; cleaned up session.", member.id)

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
