# Telegram voice messages — enablement & smoke-test checklist

**Date:** 2026-04-22
**Context:** Pivot away from Discord live voice (DAVE E2EE pain, lag). Telegram voice messages are the fast path for hands-free operation.

## TL;DR

**There is nothing to build.** L42 (`feature/voice-phase-a-messages`) landed on `develop` at commit `06e64c9` in the v0.9.0 train. The adapter, runner wiring, config flag, ffmpeg helpers, and Telegram-1-MB truncation fallback are all present. Tests exist at `tests/integration/test_telegram_voice_message.py` (happy path, truncation, STT failure, disabled-flag path) and `tests/unit/test_telegram_adapter_voice_routing.py`.

What's actually needed is to **turn it on in the operator config and smoke-test on the real device**. The telegram.log in `runtime-data.bak-2026-04-19/` shows the bot running and handling text turns, but zero voice download/`getFile` lines — so the flag has never been exercised in the live runtime.

---

## What the feature does

1. Receive `.ogg`/Opus voice note via `MessageHandler(filters.VOICE)`.
2. Download to a temp file, convert to PCM16 mono 16 kHz via `ffmpeg`.
3. Transcribe via the existing `VoicePipeline` (faster-whisper, same one Discord voice uses).
4. Feed the transcript to the orchestrator as a normal text turn.
5. Synthesize the reply with Piper TTS, re-encode to OGG/Opus at 24 kbps via `ffmpeg`, reply with `sendVoice`.
6. If the reply exceeds Telegram's 1 MB voice-note limit, iteratively shorten the audio (`ffmpeg -t` at 0.85, 0.7, 0.55, 0.4, 0.25 of original duration) and post the full text as a follow-up message so nothing is silently dropped.

Destructive tools still use the existing inline-keyboard confirmation (L23). Verbal confirmations were deferred to the abandoned Phase B.

**Relevant source:**
- `src/hestia/platforms/telegram_adapter.py` — `_handle_voice_message` (line 287), `_ogg_to_pcm` (line 453), `_pcm_chunks_to_ogg_opus` (line 477), `_truncate_ogg_to_size` (line 509).
- `src/hestia/platforms/runners.py:117` — `set_voice_deps()` injection gated on `config.telegram.voice_messages`.
- `src/hestia/config.py:112` — `TelegramConfig.voice_messages: bool = False`.
- `src/hestia/voice/pipeline.py` — shared with Discord voice.

---

## Enablement checklist

### 1. System deps

```bash
# Ubuntu / WSL
sudo apt install ffmpeg
# macOS
brew install ffmpeg
```

Verify:
```bash
ffmpeg -version | head -1
```

### 2. Python extras

```bash
uv sync --extra voice
# or
pip install 'hestia[voice]'
```

This pulls in `faster-whisper` and `piper-tts`. Core Hestia does not.

### 3. Piper voice weights

Whisper auto-downloads on first `transcribe()` call. **Piper does not.** Grab `en_US-amy-medium.onnx` and `en_US-amy-medium.onnx.json` from the Piper voice gallery and drop them in `~/.cache/hestia/voice/` (or whatever `VoiceConfig.model_cache_dir` points at).

```bash
mkdir -p ~/.cache/hestia/voice
cd ~/.cache/hestia/voice
# Files live at https://huggingface.co/rhasspy/piper-voices — grab the .onnx + .onnx.json
```

### 4. Config

```python
# in your operator config.py
from hestia.config import HestiaConfig, TelegramConfig, VoiceConfig

config = HestiaConfig(
    telegram=TelegramConfig(
        bot_token=os.environ["HESTIA_TELEGRAM_TOKEN"],  # never commit
        allowed_users=["<your-telegram-user-id>"],
        voice_messages=True,  # flip this on
    ),
    voice=VoiceConfig(
        # defaults are fine; override model_cache_dir / stt_device here if needed
    ),
    # ...
)
```

### 5. Doctor

```bash
hestia doctor
```

The `voice_prerequisites` check should come back green with "voice extra installed". It does **not** verify that Piper weights are on disk or that `ffmpeg` is on `$PATH` — both are deferred to the first voice message at runtime.

### 6. Smoke test on the real device

1. Start the bot: `hestia run --platform telegram`.
2. From your Telegram client, hold the microphone icon and record a short voice note to `@HestiaBot`. Say something deterministic, e.g. *"tell me what you are"*.
3. Watch the log for this sequence (you'll recognize it from the current log format):
   ```
   httpx INFO POST …/getFile
   httpx INFO POST http://127.0.0.1:8001/tokenize  (STT + orchestrator)
   httpx INFO POST …/chat/completions
   httpx INFO POST …/sendVoice
   ```
4. Bot should reply with a voice note. If it replies with text instead, one of the fallback branches fired — check the log for `TTS failed`, `OGG encoding failed`, or `Voice reply truncated`.

**Expected latency on RTX 3060 + Qwen 9B Q4_K_M:** ~10–15 s for a short exchange. Whisper STT dominates the first few seconds; llama.cpp is the bulk of the rest; Piper CPU encode is negligible.

### 7. Quality sanity checks

- Record a one-second "mom" to verify L42's Dylan-defined success metric: *"'mom' isn't consistently heard as 'mum'."* If it consistently hears "mum", bump the Whisper model from `medium` to `large-v3-turbo` in `VoiceConfig.stt_model`.
- Play the reply through AirPods in a noisy room. If the voice is unintelligible, try a different Piper voice (`en_US-lessac-medium`, `en_US-ryan-high`).

---

## Known gaps / likely papercuts

### 1. Whisper hallucinations on sub-word audio

The Discord voice work revealed Whisper will happily invent text for audio shorter than a syllable. The L46 patches added `_MIN_MONO16_BYTES = 8_000` (0.25 s) to the Discord sink before passing to STT. **Telegram voice messages bypass that guard entirely** — user taps-and-releases too fast, `_handle_voice_message` will still hand the decoded PCM to Whisper, and you'll get fabricated transcripts like `"Thanks for watching!"` or `"Subtitles by the Amara.org community"`.

Mitigation is small: after `pcm_bytes = await self._ogg_to_pcm(...)`, if `len(pcm_bytes) < _MIN_MONO16_BYTES` (8000 bytes == 0.25 s at 16 kHz mono 16-bit), short-circuit with a polite text reply. That's a 3-line patch in `telegram_adapter.py`. Flag for L47 if it actually bites in real use.

### 2. ffmpeg subprocess death silently drops audio

`_ogg_to_pcm` and `_pcm_chunks_to_ogg_opus` raise `RuntimeError` on non-zero return code, which is caught at the outer `try/except Exception` in `_handle_voice_message` and rendered as a generic text message to the user. That's fine, but there's no log of what ffmpeg actually complained about if you're debugging. The `stderr.decode().strip()` is in the exception text, so it's reachable, but consider bumping the `logger.warning` line to include `repr(e)` when triaging.

### 3. Confirmation UX on voice

If a voice turn triggers a destructive tool, the operator gets the inline-keyboard confirmation as a text message in the same chat. That's fine but jarring if the operator expected voice-all-the-way. Not a bug — the L42 handoff explicitly defers verbal confirmation to Phase B. Document this in the user-facing note if you add one.

### 4. Reply truncation heuristic is coarse

`_truncate_ogg_to_size` shrinks by fixed factors (0.85, 0.7, 0.55, 0.4, 0.25). For a 2 MB reply, factor 0.25 might still overshoot; the code logs a warning and sends the best attempt anyway. In practice a Piper-synthesized reply that long means the LLM answered with an essay when you asked for the weather — a prompt or `max_tokens` problem, not an encoding problem. Leave alone unless it bites.

### 5. Voice doesn't re-use the Telegram typing indicator

Text turns get a "typing…" indicator via the Matrix adapter's pattern; voice turns are silent until the full reply arrives. A 12-second silence is awkward. Consider `chat_action="record_voice"` during synthesis. Three-line patch, defer to L47 if anyone complains.

### 6. Scheduler can't reply by voice

`make_telegram_scheduler_callback` in `runners.py` always sends text. If you want the morning briefing to be a voice message, the scheduler callback needs to know whether the last platform_user turn was voice or text. Out of scope for the enablement; file an idea if you actually want it.

---

## Decisions the enablement implies

- **Discord voice branch is abandoned.** L46 stays on its feature branch as a historical artifact — do not merge to `develop`. If Discord voice ever returns, start from scratch with Pyrogram or native `discord.py` once their E2EE story stabilizes.
- **Phase B (live calls / py-tgcalls) is not needed.** Voice messages cover the dogfooding use case (hands-free voice in/out from a phone). Keep the L43 loop doc as a design sketch but don't pursue it.
- **Mumble remains on the shelf** as a future option if live duplex over Tailscale becomes a need (e.g. car mode, long-form dictation). Don't build it speculatively.

---

## Out of scope (track separately)

- **Email-to-user mapping.** Dylan asked about this in the same message. See the separate audit item — there is no email→user mapping today, and email is a *tool* (LLM pulls it) rather than an inbound platform (receives forwarded mail). Making "forward email to Hestia" work as described requires a new feature, not a config flag. Spec that out as a distinct L47-or-later loop.
- **Kimi work review** on `develop` — tracked separately.
- **README rewrite** — tracked separately.

---

## Quick-copy smoke-test commands

```bash
# On the dev box:
cd ~/hestia
uv sync --extra voice
which ffmpeg
ls ~/.cache/hestia/voice/en_US-amy-medium.onnx*

# Edit config to set telegram.voice_messages=True, then:
hestia doctor
hestia run --platform telegram

# From phone, send a voice note. Watch:
tail -f runtime-data/logs/telegram.log
```
