> **Historical note:** This handoff describes work from the v0.8.x–v0.9.0 era. Phase B (live voice calls) was later abandoned; Telegram voice messages are the supported hands-free path. The adapter code described here is production and unchanged.

# L42 Handoff — Voice Phase A: Telegram Voice Messages

**Branch:** `feature/voice-phase-a-messages`  
**Parent:** `feature/voice-shared-infra`  
**Status:** Complete, pushed to origin. Do NOT merge to `develop` until a v0.8.1+
release-prep doc names this branch in scope.

---

## What was built

A voice-message handler in the existing Telegram bot adapter.  Husband records a
voice note in Telegram, sends it to `@HestiaBot`, and gets a voice-note reply
within ~15 s.

### End-to-end flow

1. **Download** — `Message.voice.get_file()` → temp `.ogg` (Opus).
2. **Decode** — `ffmpeg` converts OGG/Opus → PCM 16 kHz mono.
3. **Transcribe** — `VoicePipeline.transcribe()` (faster-whisper).
4. **Orchestrate** — transcript is fed to `orchestrator.process_turn()` as a
   normal user text turn on the existing Telegram session.
5. **Synthesize** — `VoicePipeline.synthesize()` streams Piper PCM chunks.
6. **Encode** — `ffmpeg` merges PCM → OGG/Opus.
7. **Deliver** — `message.reply_voice()` sends the voice note back.

### Truncation fallback

If the synthesized reply exceeds Telegram's 1 MB voice-note limit, Hestia
iteratively shortens the audio with `ffmpeg -t` and sends the full text as a
follow-up message so no content is silently dropped.

### Confirmation UX

Destructive tools still pop the existing inline-keyboard confirmation (L23).
Verbal confirmations are intentionally deferred to Phase B.

---

## Files changed

| File | Change |
|------|--------|
| `src/hestia/config.py` | Added `TelegramConfig.voice_messages: bool = False` (Phase A feature flag) |
| `src/hestia/platforms/telegram_adapter.py` | Added `_handle_voice_message`, ffmpeg helpers (`_ogg_to_pcm`, `_pcm_chunks_to_ogg_opus`, `_truncate_ogg_to_size`), and `set_voice_deps()` injection point |
| `src/hestia/platforms/runners.py` | Injects orchestrator + session store into `TelegramAdapter` when `voice_messages=True` |
| `docs/guides/voice-setup.md` | New §6 documenting the feature flag, `ffmpeg` system dep, and behaviour |
| `docs/experiments/telegram-voice-smoke-test.md` | **Deleted** — subsumed by Phase A |
| `tests/integration/test_telegram_voice_message.py` | New — end-to-end mock test covering happy path, truncation, STT failure, and disabled-flag path |
| `tests/unit/test_telegram_adapter_voice_routing.py` | New — asserts VOICE handler registration conditional on flag |

---

## Test results

- `pytest tests/unit/test_telegram_adapter*.py tests/integration/test_telegram_voice_message.py` → **29 passed**
- `mypy src/hestia` → **0 errors**
- `ruff check src/` → **23 errors** (unchanged, none in modified files)

Full suite: 810 passed, 12 skipped, 1 pre-existing smoke-test flake.

---

## Dependencies

- **System:** `ffmpeg` must be on `$PATH`.
- **Python extra:** `hestia[voice]` (faster-whisper + piper-tts).
- **No new PyPI deps** — reuses the pipeline built in L41.

---

## Dylan-defined success metric (evaluated post-merge)

> Husband sends a voice message asking about the weather, gets a voice message
> back, in under 15 seconds end-to-end.
>
> Transcription quality is good enough that "mom" isn't consistently heard as
> "mum."
>
> TTS is clear enough to understand over AirPods in a noisy room.

This metric is for Dylan to evaluate after the branch eventually merges to
`develop` (post-release-prep), not as part of L42 acceptance.

---

## Next step

L43 — Voice Phase B (live calls) on `feature/voice-phase-b-calls`.
