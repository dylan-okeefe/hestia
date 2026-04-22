"""Integration tests for Telegram voice message handling.

Mocks python-telegram-bot, the voice pipeline, and ffmpeg subprocesses.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot, Message, Update, User, Voice
from telegram.ext import Application, MessageHandler, filters

from hestia.config import TelegramConfig, VoiceConfig
from hestia.core.types import Message as HestiaMessage
from hestia.platforms.telegram_adapter import TelegramAdapter


@pytest.fixture
def voice_config() -> VoiceConfig:
    return VoiceConfig()


@pytest.fixture
def telegram_config() -> TelegramConfig:
    return TelegramConfig(bot_token="test:token12345", voice_messages=True, allowed_users=["12345"])


@pytest.fixture
def adapter(telegram_config: TelegramConfig) -> TelegramAdapter:
    return TelegramAdapter(telegram_config)


def _make_mock_app() -> MagicMock:
    mock_app = MagicMock(spec=Application)
    mock_updater = AsyncMock()
    mock_app.updater = mock_updater
    return mock_app


def _make_mock_update() -> MagicMock:
    mock_update = MagicMock(spec=Update)
    mock_user = MagicMock(spec=User)
    mock_user.id = 12345
    mock_user.username = "testuser"
    mock_update.effective_user = mock_user

    mock_message = MagicMock(spec=Message)
    mock_message.text = None

    mock_voice = MagicMock(spec=Voice)
    mock_file = AsyncMock()
    mock_file.download_to_drive = AsyncMock()
    mock_voice.get_file = AsyncMock(return_value=mock_file)
    mock_message.voice = mock_voice
    mock_message.reply_voice = AsyncMock()
    mock_message.reply_text = AsyncMock()

    mock_update.effective_message = mock_message
    return mock_update


class MockPipeline:
    """Stub voice pipeline that yields deterministic results."""

    def __init__(self) -> None:
        self.transcribe_calls: list[tuple[bytes, int]] = []
        self.synthesize_calls: list[str] = []

    async def transcribe(self, pcm_bytes: bytes, *, sample_rate: int = 16000) -> str:
        self.transcribe_calls.append((pcm_bytes, sample_rate))
        return "what is the weather"

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.synthesize_calls.append(text)
        # Yield two small PCM chunks (22050 Hz, 16-bit, mono, ~0.1s each)
        yield b"\x00" * (_TTS_SAMPLE_RATE * 2 // 10)
        yield b"\x00" * (_TTS_SAMPLE_RATE * 2 // 10)


_TTS_SAMPLE_RATE = 22050


def _mock_ffmpeg_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_voice_message_full_pipeline(
    adapter: TelegramAdapter,
    voice_config: VoiceConfig,
) -> None:
    """End-to-end: voice in → STT → orchestrator → TTS → voice out."""
    mock_app = _make_mock_app()
    mock_update = _make_mock_update()
    mock_orchestrator = AsyncMock()
    mock_session_store = AsyncMock()
    mock_session = MagicMock()
    mock_session_store.get_or_create_session = AsyncMock(return_value=mock_session)

    adapter.set_voice_deps(
        orchestrator=mock_orchestrator,
        session_store=mock_session_store,
        system_prompt="You are helpful.",
        voice_config=voice_config,
    )

    stub_pipeline = MockPipeline()

    def _fake_create_subprocess(*args: str, **kwargs: Any) -> AsyncMock:
        if "s16le" in args and "libopus" in args:
            # pcm→ogg or truncation
            return _mock_ffmpeg_process(stdout=b"FAKE_OGG_DATA")
        return _mock_ffmpeg_process(stdout=b"\x00" * 10_000)

    with patch(
        "hestia.platforms.telegram_adapter.Application.builder",
        return_value=MagicMock(
            token=MagicMock(
                return_value=MagicMock(
                    http_version=MagicMock(
                        return_value=MagicMock(build=MagicMock(return_value=mock_app))
                    )
                )
            )
        ),
    ):
        with patch(
            "hestia.platforms.telegram_adapter.get_voice_pipeline",
            AsyncMock(return_value=stub_pipeline),
        ):
            with patch(
                "hestia.platforms.telegram_adapter.asyncio.create_subprocess_exec",
                side_effect=_fake_create_subprocess,
            ):
                await adapter.start(lambda p, u, t: None)
                await adapter._handle_voice_message(mock_update, None)

                # Assert session was retrieved
                mock_session_store.get_or_create_session.assert_called_once_with("telegram", "12345")

                # Assert orchestrator was called with the transcript
                assert mock_orchestrator.process_turn.call_count == 1
                call_kwargs = mock_orchestrator.process_turn.call_args[1]
                assert call_kwargs["session"] == mock_session
                assert call_kwargs["user_message"].content == "what is the weather"
                assert call_kwargs["system_prompt"] == "You are helpful."

                # Extract the respond callback and invoke it to exercise TTS path
                respond_callback = call_kwargs["respond_callback"]
                await respond_callback("It is sunny today.")

    # Assert synthesize was called with the response text
    assert stub_pipeline.synthesize_calls == ["It is sunny today."]

    # Assert voice reply was sent
    mock_update.effective_message.reply_voice.assert_called_once()
    call_args = mock_update.effective_message.reply_voice.call_args[1]
    assert "voice" in call_args

    await adapter.stop()


@pytest.mark.asyncio
async def test_voice_message_truncation_when_over_1mb(
    adapter: TelegramAdapter,
    voice_config: VoiceConfig,
) -> None:
    """If synthesized OGG exceeds 1 MB, truncation + text fallback is triggered."""
    mock_app = _make_mock_app()
    mock_update = _make_mock_update()
    mock_orchestrator = AsyncMock()
    mock_session_store = AsyncMock()
    mock_session = MagicMock()
    mock_session_store.get_or_create_session = AsyncMock(return_value=mock_session)

    adapter.set_voice_deps(
        orchestrator=mock_orchestrator,
        session_store=mock_session_store,
        system_prompt="You are helpful.",
        voice_config=voice_config,
    )

    stub_pipeline = MockPipeline()

    large_ogg = b"X" * 1_500_000
    small_ogg = b"Y" * 800_000

    def _fake_create_subprocess(*args: str, **kwargs: Any) -> AsyncMock:
        if "s16le" in args and "libopus" in args and "-t" not in args:
            # pcm→ogg: return oversized
            return _mock_ffmpeg_process(stdout=large_ogg)
        if "-t" in args:
            # truncation attempt
            return _mock_ffmpeg_process(stdout=small_ogg)
        return _mock_ffmpeg_process(stdout=b"\x00" * 10_000)

    with patch(
        "hestia.platforms.telegram_adapter.Application.builder",
        return_value=MagicMock(
            token=MagicMock(
                return_value=MagicMock(
                    http_version=MagicMock(
                        return_value=MagicMock(build=MagicMock(return_value=mock_app))
                    )
                )
            )
        ),
    ):
        with patch(
            "hestia.platforms.telegram_adapter.get_voice_pipeline",
            AsyncMock(return_value=stub_pipeline),
        ):
            with patch(
                "hestia.platforms.telegram_adapter.asyncio.create_subprocess_exec",
                side_effect=_fake_create_subprocess,
            ):
                await adapter.start(lambda p, u, t: None)
                await adapter._handle_voice_message(mock_update, None)

                # Invoke respond callback to trigger truncation path
                respond_callback = mock_orchestrator.process_turn.call_args[1]["respond_callback"]
                await respond_callback("A very long response that exceeds one megabyte.")

    # Assert both voice and text fallback were sent
    assert mock_update.effective_message.reply_voice.call_count == 1
    assert mock_update.effective_message.reply_text.call_count == 1
    text_call = mock_update.effective_message.reply_text.call_args[0][0]
    assert "truncated" in text_call.lower()
    assert "A very long response that exceeds one megabyte." in text_call

    await adapter.stop()


@pytest.mark.asyncio
async def test_voice_message_disabled_when_flag_false() -> None:
    """When voice_messages=False, the voice handler no-ops and pipeline is never invoked."""
    cfg = TelegramConfig(bot_token="test:token12345", voice_messages=False)
    adapter = TelegramAdapter(cfg)

    mock_update = _make_mock_update()

    with patch(
        "hestia.platforms.telegram_adapter.get_voice_pipeline",
        AsyncMock(side_effect=Exception("should not be called")),
    ):
        # Should return early without touching the pipeline
        await adapter._handle_voice_message(mock_update, None)

    # No reply should be sent since the handler returns before any async work
    mock_update.effective_message.reply_voice.assert_not_called()
    mock_update.effective_message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_voice_message_stt_failure(
    adapter: TelegramAdapter,
    voice_config: VoiceConfig,
) -> None:
    """If STT fails, the adapter replies with a text error and does not call the orchestrator."""
    mock_app = _make_mock_app()
    mock_update = _make_mock_update()
    mock_orchestrator = AsyncMock()
    mock_session_store = AsyncMock()

    adapter.set_voice_deps(
        orchestrator=mock_orchestrator,
        session_store=mock_session_store,
        system_prompt="You are helpful.",
        voice_config=voice_config,
    )

    with patch(
        "hestia.platforms.telegram_adapter.Application.builder",
        return_value=MagicMock(
            token=MagicMock(
                return_value=MagicMock(
                    http_version=MagicMock(
                        return_value=MagicMock(build=MagicMock(return_value=mock_app))
                    )
                )
            )
        ),
    ):
        with patch(
            "hestia.platforms.telegram_adapter.get_voice_pipeline",
            AsyncMock(side_effect=RuntimeError("STT model not found")),
        ):
            with patch(
                "hestia.platforms.telegram_adapter.asyncio.create_subprocess_exec",
                return_value=_mock_ffmpeg_process(stdout=b"\x00" * 10_000),
            ):
                await adapter.start(lambda p, u, t: None)
                await adapter._handle_voice_message(mock_update, None)

    mock_orchestrator.process_turn.assert_not_called()
    mock_update.effective_message.reply_text.assert_called_once()
    reply = mock_update.effective_message.reply_text.call_args[0][0]
    assert "couldn't understand" in reply.lower()

    await adapter.stop()
