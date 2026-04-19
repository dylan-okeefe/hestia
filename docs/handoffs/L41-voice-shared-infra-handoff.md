# L41 — Voice shared infrastructure handoff

## Scope

Transport-agnostic audio pipeline (STT + TTS), VAD stub, voice configuration,
`hestia[voice]` extra, doctor check, setup guide, and unit tests.
Zero user-facing behavior change — no adapter calls the pipeline yet.

## Files touched

| File | Commit | Change |
|------|--------|--------|
| `src/hestia/errors.py` | 1 | Added `MissingExtraError`. |
| `src/hestia/voice/__init__.py` | 1 | Package init exporting `VoicePipeline`, `get_voice_pipeline`. |
| `src/hestia/voice/pipeline.py` | 1 | `VoicePipeline` dataclass with lazy STT/TTS init, sentence-level TTS streaming, singleton accessor, gated imports. |
| `src/hestia/voice/vad.py` | 2 | `SileroVAD` stub — yields the full stream as one segment. |
| `src/hestia/config.py` | 2 | Added `VoiceConfig` dataclass; wired into `HestiaConfig.voice`. |
| `pyproject.toml` | 3 | Added `voice` extra (`faster-whisper`, `piper-tts`); bumped version `0.8.0` → `0.8.1.dev0`. |
| `uv.lock` | 3 | Regenerated with voice extra dependencies. |
| `src/hestia/doctor.py` | 3 | Added `_check_voice_prerequisites` using `importlib.util.find_spec`. |
| `docs/guides/voice-setup.md` | 3 | Concise setup guide: install extra, model auto-download, Piper voices, VRAM budget, doctor check. |
| `tests/unit/test_voice_pipeline.py` | 4 | Five test cases: lazy load, sentence chunks, singleton, first-call config requirement, import-without-extra safety. |

## Mock/test strategy

- `faster_whisper.WhisperModel` and `piper.PiperVoice` are patched at
  `hestia.voice.pipeline.*` namespace.
- Tests run **without** `[voice]` installed, proving the import-time-safe
  contract.
- `_PIPELINE` singleton is reset by an autouse fixture to avoid cross-test
  state leaks.

## VRAM headroom check

Documented in `voice-setup.md` for RTX 3060 12 GB + Qwen 9B Q4_K_M:
~5.5 GB LLM + ~1.6 GB Whisper int8 + 0 GB Piper (CPU) = ~7.1 GB used,
~4.9 GB headroom.

## What L42 and L43 will plug into

- **L42** (Phase A — Telegram voice messages) will import `get_voice_pipeline`
  from `hestia.voice.pipeline` and call `transcribe()` / `synthesize()` in the
  Telegram bot voice-message handler.
- **L43** (Phase B — Telegram voice calls) will replace the `SileroVAD` stub
  with real voice-activity segmentation and add streaming integration via
  py-tgcalls.
- Both phases fork from `feature/voice-shared-infra`, not from `develop`.

## Quality gate

- **Tests:** 798 passed, 6 skipped (+9 from new test file; baseline 789 unchanged)
- **Mypy:** 0 errors in 95 source files
- **Ruff:** 23 errors in `src/` (baseline unchanged)
- **Doctor:** `hestia doctor` runs cleanly whether `[voice]` is installed or not

## Branch / merge discipline

- Branch: `feature/voice-shared-infra`
- Pushed to `origin/feature/voice-shared-infra`
- **Do NOT merge to `develop`** until a v0.8.1+ release-prep doc names it in scope.
