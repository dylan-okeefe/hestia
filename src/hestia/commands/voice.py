"""Voice-related command implementations."""

from __future__ import annotations

import math
import struct
import subprocess

import click

from hestia.app import AppContext
from hestia.config import VoiceConfig
from hestia.voice.pipeline import VoicePipeline

_SMOKE_TEXT = "Voice pipeline smoke check."
_STT_TONE_SECONDS = 1.5
_STT_TONE_HZ = 440.0
# Warn (not fail) when the STT GPU has less than this free. The STT
# round-trip itself is the real allocation test; this is diagnostics.
_STT_VRAM_WARN_MIB = 1024


def _tone_pcm(duration_s: float = _STT_TONE_SECONDS, freq: float = _STT_TONE_HZ) -> bytes:
    """Raw PCM16 mono sine tone as a stand-in for captured speech."""
    sample_rate = 16000
    n = int(duration_s * sample_rate)
    return b"".join(
        struct.pack("<h", int(0.3 * 32767 * math.sin(2 * math.pi * freq * i / sample_rate)))
        for i in range(n)
    )


def _gpu_free_mib(device_index: int) -> int | None:
    """Best-effort free VRAM (MiB) for a GPU via nvidia-smi; None if unknown."""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if device_index >= len(lines):
        return None
    try:
        return int(lines[device_index])
    except ValueError:
        return None


async def _run_voice_smoke(config: VoiceConfig) -> list[str]:
    """Round-trip the voice pipeline (STT + TTS).

    Returns a list of failure descriptions; empty means everything passed.
    A tone is used for STT (empty transcript is expected — the point is
    that the model loads and runs on the configured device without OOM),
    and TTS output is checked for non-empty PCM.
    """
    failures: list[str] = []
    pipeline = VoicePipeline(config=config)

    if config.stt_device == "cuda":
        free = _gpu_free_mib(config.stt_device_index)
        if free is not None:
            level = "warn" if free < _STT_VRAM_WARN_MIB else "ok"
            click.echo(f"STT GPU free VRAM before load: {free} MiB ({level})")

    try:
        transcript = await pipeline.transcribe(_tone_pcm(), sample_rate=16000)
        click.echo(f"STT ok (tone -> {transcript.strip()!r}; empty is expected)")
    except Exception as e:  # noqa: BLE001 - report any STT failure
        failures.append(f"STT failed on {config.stt_device}:{config.stt_device_index}: {e}")

    try:
        chunks = [chunk async for chunk in pipeline.synthesize(_SMOKE_TEXT)]
        total = sum(len(chunk) for chunk in chunks)
        if total == 0:
            failures.append("TTS produced no audio")
        else:
            click.echo(f"TTS ok ({len(chunks)} chunks, {total} bytes PCM16)")
    except Exception as e:  # noqa: BLE001 - report any TTS failure
        failures.append(f"TTS failed on {config.tts_device or 'engine-default'}: {e}")
        return failures

    # The 2026-09-09 production regression: kokoro silently grabbed CUDA
    # despite tts_device="cpu". If TTS is configured for CPU it must not
    # hold any CUDA memory after synthesis.
    if config.tts_engine == "kokoro" and (config.tts_device or "cpu") == "cpu":
        try:
            import torch

            allocated = torch.cuda.memory_allocated() if torch.cuda.is_available() else 0
        except Exception:  # noqa: BLE001 - torch not installed or no CUDA
            allocated = 0
        if allocated > 0:
            failures.append(
                f"TTS allocated {allocated} bytes of CUDA memory despite tts_device=cpu"
            )

    return failures


async def cmd_voice_smoke(app: AppContext) -> None:
    """Smoke-test the voice pipeline (STT + TTS) against the live config."""
    config = app.config.voice
    click.echo(
        f"Voice smoke: stt={config.stt_model} on {config.stt_device}:{config.stt_device_index}, "
        f"tts={config.tts_engine}/{config.tts_voice} on {config.tts_device or 'engine-default'}"
    )
    failures = await _run_voice_smoke(config)
    if failures:
        for failure in failures:
            click.echo(f"FAIL: {failure}", err=True)
        click.echo("voice smoke: FAILED", err=True)
        raise SystemExit(1)
    click.echo("voice smoke: OK")
