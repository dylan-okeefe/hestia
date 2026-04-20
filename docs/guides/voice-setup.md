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

## 6. Enabling voice messages on Telegram (Phase A)

Hestia can receive and reply with voice messages via the existing Telegram bot.
This is a lightweight stepping-stone toward live voice calls (Phase B).

### Requirements

- The `[voice]` extra must be installed (see §1).
- **System `ffmpeg`** must be available on `$PATH`.  Hestia uses it to convert
  between Telegram's OGG/Opus format and the PCM used by the STT/TTS models.
  Install with your package manager:
  ```bash
  # Debian/Ubuntu
  sudo apt install ffmpeg
  # macOS
  brew install ffmpeg
  ```

### Configuration

Set the feature flag in your config file:

```python
from hestia.config import HestiaConfig, TelegramConfig

config = HestiaConfig(
    telegram=TelegramConfig(
        bot_token="...",
        allowed_users=["..."],
        voice_messages=True,  # <-- enable Phase A
    ),
)
```

No extra credentials are needed — voice messages reuse the existing
`telegram.bot_token`.

### Behaviour

- When a user sends a voice note to `@HestiaBot`, the bot downloads the audio,
  transcribes it with Whisper, feeds the transcript to the orchestrator as a
  normal text turn, synthesizes the response with Piper, and replies with a
  voice note of its own.
- Replies that would exceed Telegram's 1 MB voice-note limit are truncated;
  the full text is sent as a follow-up text message.
- Destructive tools still require the usual inline-keyboard confirmation
  (verbal confirmations are a Phase B feature).

### What's next

Phase B adds **live voice calls** via Pyrogram + py-tgcalls.  See
`docs/development-process/kimi-loops/L43-voice-phase-b-calls.md` for the spec.
