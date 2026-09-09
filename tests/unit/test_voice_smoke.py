"""Tests for the voice-smoke command (src/hestia/commands/voice.py)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hestia.commands.voice import _gpu_free_mib, _run_voice_smoke
from hestia.config import VoiceConfig


def _voice_config(tmp_path: Any, **overrides: Any) -> VoiceConfig:
    params: dict[str, Any] = {
        "stt_model": "tiny",
        "stt_device": "cpu",
        "stt_compute_type": "int8",
        "tts_engine": "kokoro",
        "tts_voice": "am_puck",
        "tts_device": "cpu",
        "model_cache_dir": tmp_path / "voice_cache",
    }
    params.update(overrides)
    return VoiceConfig(**params)


class TestRunVoiceSmoke:
    @pytest.mark.anyio
    async def test_passes_when_stt_and_tts_round_trip(self, tmp_path: Any) -> None:
        import numpy as np

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([MagicMock(text="")], None)
        fake_kpipeline = MagicMock()
        fake_kpipeline.return_value = [
            ("", "", np.array([0.0, 0.5], dtype=np.float32)),
        ]

        with (
            patch("hestia.voice.pipeline.WhisperModel", return_value=fake_model),
            patch("hestia.voice.pipeline.KPipeline", return_value=fake_kpipeline),
            # TTS is cpu-configured; torch may not even be installed here.
            patch("hestia.commands.voice._gpu_free_mib", return_value=None),
        ):
            failures = await _run_voice_smoke(_voice_config(tmp_path))

        assert failures == []

    @pytest.mark.anyio
    async def test_stt_failure_is_reported(self, tmp_path: Any) -> None:
        import numpy as np

        fake_kpipeline = MagicMock()
        fake_kpipeline.return_value = [
            ("", "", np.array([0.0], dtype=np.float32)),
        ]

        with (
            patch(
                "hestia.voice.pipeline.WhisperModel",
                side_effect=RuntimeError("CUDA out of memory"),
            ),
            patch("hestia.voice.pipeline.KPipeline", return_value=fake_kpipeline),
        ):
            failures = await _run_voice_smoke(_voice_config(tmp_path))

        assert any("STT failed" in failure and "out of memory" in failure for failure in failures)

    @pytest.mark.anyio
    async def test_tts_failure_is_reported(self, tmp_path: Any) -> None:
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([MagicMock(text="")], None)

        with (
            patch("hestia.voice.pipeline.WhisperModel", return_value=fake_model),
            patch(
                "hestia.voice.pipeline.KPipeline",
                side_effect=RuntimeError("CUDA out of memory"),
            ),
        ):
            failures = await _run_voice_smoke(_voice_config(tmp_path))

        assert any("TTS failed" in failure for failure in failures)

    @pytest.mark.anyio
    async def test_empty_tts_output_is_reported(self, tmp_path: Any) -> None:
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([MagicMock(text="")], None)
        fake_kpipeline = MagicMock()
        fake_kpipeline.return_value = []  # no chunks at all

        with (
            patch("hestia.voice.pipeline.WhisperModel", return_value=fake_model),
            patch("hestia.voice.pipeline.KPipeline", return_value=fake_kpipeline),
        ):
            failures = await _run_voice_smoke(_voice_config(tmp_path))

        assert any("no audio" in failure for failure in failures)

    @pytest.mark.anyio
    async def test_cpu_tts_holding_cuda_memory_is_reported(self, tmp_path: Any) -> None:
        """The 2026-09-09 production regression, as a unit test."""
        import numpy as np

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([MagicMock(text="")], None)
        fake_kpipeline = MagicMock()
        fake_kpipeline.return_value = [
            ("", "", np.array([0.0], dtype=np.float32)),
        ]

        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = True
        fake_torch.cuda.memory_allocated.return_value = 12345678

        with (
            patch("hestia.voice.pipeline.WhisperModel", return_value=fake_model),
            patch("hestia.voice.pipeline.KPipeline", return_value=fake_kpipeline),
            patch.dict("sys.modules", {"torch": fake_torch}),
        ):
            failures = await _run_voice_smoke(_voice_config(tmp_path))

        assert any("CUDA memory despite tts_device=cpu" in failure for failure in failures)


class TestGpuFreeMib:
    def test_parses_nvidia_smi_output(self, tmp_path: Any) -> None:
        import subprocess

        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1845\n918\n"
        )
        with patch("hestia.commands.voice.subprocess.run", return_value=fake_proc):
            assert _gpu_free_mib(0) == 1845
            assert _gpu_free_mib(1) == 918

    def test_returns_none_when_index_out_of_range(self, tmp_path: Any) -> None:
        import subprocess

        fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="1845\n")
        with patch("hestia.commands.voice.subprocess.run", return_value=fake_proc):
            assert _gpu_free_mib(3) is None

    def test_returns_none_when_nvidia_smi_missing(self, tmp_path: Any) -> None:
        with patch(
            "hestia.commands.voice.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert _gpu_free_mib(0) is None
