"""Transport-agnostic audio pipeline (STT + TTS).

Models are loaded lazily on first use.  The module is safe to import even when
``hestia[voice]`` is not installed — the missing-extra error is raised only
when a model is actually needed.
"""

from __future__ import annotations

import asyncio
import io
import re
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hestia.errors import MissingExtraError

if TYPE_CHECKING:
    from hestia.config import VoiceConfig

# Gated imports — module remains importable when extras are absent.
try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None

try:
    from piper import PiperVoice
except ImportError:  # pragma: no cover
    PiperVoice = None  # type: ignore[misc,assignment]


@dataclass
class VoicePipeline:
    """Lazy-loading STT/TTS pipeline."""

    config: VoiceConfig
    _whisper_model: object | None = None
    _tts_voice: object | None = None
    _stt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _tts_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def transcribe(self, pcm_bytes: bytes, *, sample_rate: int = 16000) -> str:
        """Transcribe raw PCM16 mono audio to text."""
        await self._ensure_stt_loaded()
        wav = _pcm_to_wav(pcm_bytes, sample_rate)
        return await asyncio.to_thread(self._transcribe_sync, wav)

    def _transcribe_sync(self, wav: io.BytesIO) -> str:
        segments, _info = self._whisper_model.transcribe(wav)  # type: ignore[attr-defined]
        return "".join(seg.text for seg in segments).strip()

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Stream TTS audio chunks (sentence-level granularity)."""
        await self._ensure_tts_loaded()
        sentences = _split_sentences(text)
        for sentence in sentences:
            audio = await asyncio.to_thread(self._synthesize_sentence, sentence)
            yield audio

    def _synthesize_sentence(self, sentence: str) -> bytes:
        audio_bytes = b""
        # PiperVoice.synthesize returns a generator of AudioChunk objects
        for chunk in self._tts_voice.synthesize(sentence):  # type: ignore[attr-defined]
            audio_bytes += chunk.audio_int16_bytes
        return audio_bytes

    async def _ensure_stt_loaded(self) -> None:
        async with self._stt_lock:
            if self._whisper_model is not None:
                return
            if WhisperModel is None:
                raise MissingExtraError("Install hestia[voice] for STT support")
            self._whisper_model = await asyncio.to_thread(
                WhisperModel,
                self.config.stt_model,
                device=self.config.stt_device,
                compute_type=self.config.stt_compute_type,
                download_root=str(self.config.model_cache_dir),
            )

    async def _ensure_tts_loaded(self) -> None:
        async with self._tts_lock:
            if self._tts_voice is not None:
                return
            if self.config.tts_engine == "piper":
                if PiperVoice is None:
                    raise MissingExtraError("Install hestia[voice] for TTS support")
                self._tts_voice = await asyncio.to_thread(_load_piper_voice, self.config)
            else:
                raise MissingExtraError(
                    f"TTS engine '{self.config.tts_engine}' not supported"
                )


_PIPELINE: VoicePipeline | None = None
_PIPELINE_LOCK = asyncio.Lock()


async def get_voice_pipeline(config: VoiceConfig | None = None) -> VoicePipeline:
    """Process-wide singleton.  Lazy first-init under a lock."""
    global _PIPELINE
    async with _PIPELINE_LOCK:
        if _PIPELINE is None:
            if config is None:
                raise RuntimeError("First call must pass a VoiceConfig")
            _PIPELINE = VoicePipeline(config=config)
    return _PIPELINE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int) -> io.BytesIO:
    """Wrap raw PCM16 mono bytes in an in-memory WAV file."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,  # SubChunk1Size
        1,  # AudioFormat (PCM)
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return io.BytesIO(header + pcm_bytes)


_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$(?=\s*)")


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter; sufficient for v1."""
    sentences = [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]
    return sentences if sentences else [text.strip()]


def _load_piper_voice(config: VoiceConfig) -> object:
    model_path = config.model_cache_dir / f"{config.tts_voice}.onnx"
    return PiperVoice.load(str(model_path))
