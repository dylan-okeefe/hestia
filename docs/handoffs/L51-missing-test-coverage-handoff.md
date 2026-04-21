# L51 — Missing test coverage bundle handoff

## Scope

Close the highest-impact test coverage gaps identified in the audit.

## Files touched

| File | Change |
|------|--------|
| `tests/unit/test_platform_runners.py` | **New.** Tests for platform allow-list routing, startup/shutdown lifecycle, signal handling, scheduler callback routing, and confirm callback wiring. Mock-based (no real Telegram/Matrix). |
| `tests/unit/test_memory_epochs.py` | **Extended.** Added `TestMemoryEpochCompilerMockStore` with mock-`MemoryStore` tests for deduplication, token truncation, and tag-filter fetch parameter pass-through. |
| `tests/unit/test_voice_vad.py` | **New.** Tests for `SileroVAD` stub: single-segment output and empty-stream no-op behavior. |
| `tests/unit/test_reflection_prompts.py` | **New.** Tests that all prompt templates exist, are non-empty, contain expected sections, and have no accidental f-string placeholders. |
| `tests/unit/test_orchestrator_confirmation.py` | **Modified.** Added `context_builder.build` assertion in happy-path test (removed after review: `process_turn` calls it twice on tool-call paths). |
| `tests/unit/test_orchestrator_artifact_accumulation.py` | **Modified.** Added `context_builder.build` assertion (removed after review: same double-call reason). |
| `tests/unit/test_orchestrator_errors.py` | **Modified.** Added `mock_context_builder.build.assert_called_once()` and `mock_inference.chat.assert_called_once()` to `test_post_done_respond_callback_error_no_illegal_transition`. |
| `tests/e2e/conftest.py` | **Modified.** `matrix_test_client` fixture now creates the client before skipping, and `_responses` is cleared in `finally` cleanup. Removed unused `sys`/`Any` imports and unused `localpart` variable. |

## Test results

- **New tests:** 36 passed (platform runners 16, memory epochs 9, voice VAD 3, reflection prompts 4)
- **Orchestrator tests:** 19 passed
- **E2E tests:** 6 skipped (Synapse unavailable)
- **Total affected:** 47 passed, 0 failed, 6 skipped

## Quality gate

- **Mypy:** 14 errors in `src/hestia` — all pre-existing baseline (config.py, voice/pipeline.py, discord_voice_runner.py)
- **Ruff:** No new issues introduced in changed files; baseline unchanged

## What was deferred / not done

- `commands.py` tests deferred to L50 (commands split will change structure).
- `context/builder.py` decomposition tests deferred to L52.
- `test_orchestrator_concurrent_tools.py` had no appropriate place for `inference.chat.assert_called_once()` because it tests `_execute_tool_calls` directly (no `process_turn` / no inference call).
- `test_orchestrator_confirmation.py` and `test_orchestrator_artifact_accumulation.py` happy-path tests call `context_builder.build` twice (initial turn + post-tool turn), so `assert_called_once()` was not appropriate.

## Branch / merge discipline

- Branch: `feature/l51-missing-test-coverage`
- **Do NOT merge to `develop`** until release-prep merge sequence.
