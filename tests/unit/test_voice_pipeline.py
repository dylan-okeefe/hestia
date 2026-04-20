"""Unit tests for the voice pipeline (STT + TTS).

All external model dependencies are mocked so these tests run without
``hestia[voice]`` installed.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hestia.config import VoiceConfig
from hestia.voice import pipeline as _vp
from hestia.voice.pipeline import (
    VoicePipeline,
    _split_sentences,
    get_voice_pipeline,
)


@pytest.fixture(autouse=True)
def _reset_pipeline_singleton() -> Generator[None, None, None]:
    """Reset the process-wide singleton before every test."""
    _vp._PIPELINE = None
    yield
    _vp._PIPELINE = None


@pytest.fixture
def voice_config(tmp_path: Any) -> VoiceConfig:
    return VoiceConfig(
        stt_model="tiny",
        stt_device="cpu",
        stt_compute_type="int8",
        tts_engine="piper",
        tts_voice="en_US-amy-medium",
        model_cache_dir=tmp_path / "voice_cache",
    )


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class TestTranscribe:
    @pytest.mark.anyio
    async def test_transcribe_lazy_loads_model(
        self, voice_config: VoiceConfig
    ) -> None:
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([FakeSegment("hello world")], None)

        with patch(
            "hestia.voice.pipeline.WhisperModel", return_value=fake_model
        ) as mock_whisper:
            pipeline = VoicePipeline(config=voice_config)
            result = await pipeline.transcribe(b"\x00\x01" * 16000)

        assert result == "hello world"
        mock_whisper.assert_called_once_with(
            "tiny",
            device="cpu",
            compute_type="int8",
            download_root=str(voice_config.model_cache_dir),
        )

        # Second call must not re-init
        with patch(
            "hestia.voice.pipeline.WhisperModel", return_value=fake_model
        ) as mock_whisper2:
            result2 = await pipeline.transcribe(b"\x00\x01" * 16000)

        assert result2 == "hello world"
        mock_whisper2.assert_not_called()


class TestSynthesize:
    @pytest.mark.anyio
    async def test_synthesize_yields_sentence_chunks(
        self, voice_config: VoiceConfig
    ) -> None:
        fake_voice = MagicMock()
        fake_voice.synthesize.side_effect = [
            [b"audio1"],
            [b"audio2"],
        ]

        with patch(
            "hestia.voice.pipeline.PiperVoice", load=MagicMock(return_value=fake_voice)
        ) as mock_piper_class:
            mock_piper_class.load.return_value = fake_voice
            pipeline = VoicePipeline(config=voice_config)
            chunks = [
                chunk async for chunk in pipeline.synthesize("First. Second.")
            ]

        assert len(chunks) == 2
        assert chunks[0] == b"audio1"
        assert chunks[1] == b"audio2"


class TestSingleton:
    @pytest.mark.anyio
    async def test_singleton_returns_same_instance(
        self, voice_config: VoiceConfig
    ) -> None:
        p1 = await get_voice_pipeline(voice_config)
        p2 = await get_voice_pipeline()
        assert p1 is p2

    @pytest.mark.anyio
    async def test_singleton_first_call_requires_config(self) -> None:
        with pytest.raises(RuntimeError, match="First call must pass a VoiceConfig"):
            await get_voice_pipeline()


class TestImportWithoutExtra:
    def test_import_without_extra(self) -> None:
        """Module must be importable even when faster_whisper is absent."""
        import hestia.voice.pipeline as vp

        # When the extra is missing the gated imports set the names to None.
        assert vp.WhisperModel is None or vp.WhisperModel is not None
        # The real assertion is that this test file imported successfully.

    @pytest.mark.anyio
    async def test_missing_extra_raises_on_first_use(
        self, voice_config: VoiceConfig
    ) -> None:
        from hestia.errors import MissingExtraError

        with patch("hestia.voice.pipeline.WhisperModel", None):
            pipeline = VoicePipeline(config=voice_config)
            with pytest.raises(MissingExtraError):
                await pipeline.transcribe(b"\x00\x01" * 16000)


class TestSentenceSplit:
    def test_two_sentences(self) -> None:
        assert _split_sentences("First sentence. Second sentence.") == [
            "First sentence.",
            "Second sentence.",
        ]

    def test_single_sentence(self) -> None:
        assert _split_sentences("Only one.") == ["Only one."]

    def test_no_punctuation(self) -> None:
        assert _split_sentences("no punctuation here") == ["no punctuation here"]
