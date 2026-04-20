# Voice Setup Guide

Hestia's voice pipeline provides local STT (speech-to-text) and TTS
(text-to-speech) using open-source models.  All inference happens on your
machine — no audio leaves the network.

## 1. Install the extra

```bash
pip install hestia[voice]
# or, if you use uv:
uv sync --extra voice
```

Core Hestia (`pip install hestia`) does **not** pull in voice dependencies.

## 2. Model auto-download

The first call to `transcribe()` downloads faster-whisper weights
(~1.6 GB for `large-v3-turbo`) to:

```
~/.cache/hestia/voice/
```

Override the path via `VoiceConfig.model_cache_dir`.

## 3. Piper voices

Piper voices are **not** auto-downloaded.  Download your chosen voice
(e.g. `en_US-amy-medium`) from the
[Piper voice gallery](https://rhasspy.github.io/piper-samples/):

- `en_US-amy-medium.onnx`
- `en_US-amy-medium.onnx.json`

Place both files in `~/.cache/hestia/voice/` (or your custom
`model_cache_dir`).

## 4. VRAM budget (example: RTX 3060 12 GB)

| Component         | VRAM   | Notes                     |
|-------------------|--------|---------------------------|
| Qwen 9B Q4_K_M    | ~5.5 GB| Typical local LLM         |
| Whisper int8      | ~1.6 GB| STT model                 |
| Piper             | 0 GB   | Runs on CPU               |
| **Total used**    | ~7.1 GB|                           |
| **Headroom**      | ~4.9 GB| For KV cache + activations|

If VRAM is tight, switch to a smaller whisper model (`medium`, `small`) or
run Whisper on CPU (`stt_device="cpu"`).

## 5. Doctor check

```bash
hestia doctor
```

The `voice_prerequisites` check reports:

- **green + "voice extra not installed"** — expected when `[voice]` is absent.
- **green + "voice extra installed"** — both `faster-whisper` and `piper-tts`
  resolved.
- **red** — partial install (e.g. `faster-whisper` present but `piper-tts`
  missing).
