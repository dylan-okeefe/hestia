# L95 — Split VoicePipeline STT/TTS Init Locks

**Status:** Spec only
**Branch:** `feature/l95-voice-split-locks` (from `develop`)

## Intent

The `VoicePipeline` class uses a single `_init_lock` for both STT (speech-to-text) and TTS (text-to-speech) model initialization. This means that if a voice message arrives while TTS is initializing (e.g., for a proactive notification), the STT init blocks until TTS finishes — even though they're independent models loaded into different memory. The impact is "TTS starts late once, ever" on the first voice message if STT is loading concurrently, or vice versa.

This is low severity (it only affects the very first voice interaction), but it's a correctness issue — two independent resources should not share a serialization lock. Splitting the lock is trivial and prevents a class of future bugs if model loading ever becomes slower (e.g., larger Whisper models).

## Scope

### §1 — Split `_init_lock` into `_stt_lock` and `_tts_lock`

Find the `VoicePipeline` class (likely in `src/hestia/voice/` or `src/hestia/platforms/voice/`). Locate the single `_init_lock: asyncio.Lock`.

Replace:
```python
self._init_lock = asyncio.Lock()
```

With:
```python
self._stt_lock = asyncio.Lock()
self._tts_lock = asyncio.Lock()
```

Then find every usage of `_init_lock`:
- If it guards STT initialization (Whisper model loading), change to `self._stt_lock`
- If it guards TTS initialization, change to `self._tts_lock`
- If there's a combined init path that loads both, split it into two sequential lock acquisitions

**Important:** Do NOT use a single lock for both. The whole point is that STT and TTS can initialize concurrently.

**Commit:** `fix(voice): split STT/TTS init locks for concurrent loading`

## Evaluation

- **Spec check:** `VoicePipeline` has two separate locks, one for STT and one for TTS. No code path acquires a single lock that guards both models.
- **Intent check:** STT initialization does not block on TTS initialization, and vice versa. On a fresh start, if a voice message arrives during TTS init, STT can begin loading immediately without waiting.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. If there are voice pipeline tests, they still pass.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `grep -n "_init_lock" src/hestia/` returns 0 results (the old lock is fully replaced)
- `.kimi-done` includes `LOOP=L95`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
