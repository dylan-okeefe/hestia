# L51 — Missing test coverage bundle

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l51-missing-test-coverage` (from `develop`)

## Goal

Close the highest-impact test coverage gaps identified in the audit.

## Scope

### Priority 1: `src/hestia/platforms/runners.py` (254 lines)
- Production entry point for every platform loop.
- Test: platform allow-list routing, startup/shutdown lifecycle, signal handling.
- Mock the platform adapters; don't need real Matrix/Telegram/Discord.

### Priority 2: `src/hestia/memory/epochs.py` (memory context compiler)
- `MemoryEpochCompiler.compile` is included in every turn prompt but has zero tests.
- Test: empty DB returns empty string, dedup behavior, token-truncation, tag-filter.
- Use a mock or in-memory `MemoryStore`.

### Priority 3: `src/hestia/voice/vad.py`
- Stub VAD passes stream as one segment — behavior is load-bearing.
- Test: single-segment output, no-op for empty stream.

### Priority 4: `src/hestia/reflection/prompts.py`
- Prompt templates with variable substitution.
- Test: all templates render without KeyError on valid input.

### Priority 5: Orchestrator `assert_called_once()` assertions
- Add `inference.chat.assert_called_once()` to happy-path orchestrator tests.
- Add `context_builder.build.assert_called_once()` before `inference.chat` in existing tests (§5.4).

### Priority 6: `tests/e2e/conftest.py` response list cleanup
- `HestiaMatrixTestClient._responses` accumulates across tests.
- Add a fixture cleanup to reset between tests.

## Out of scope
- `commands.py` tests (deferred to L50 — commands split will change structure).
- `context/builder.py` decomposition tests (deferred to L52).
- Platform-specific e2e flows (already covered by existing e2e).

## Tests

- New test files:
  - `tests/unit/test_platform_runners.py`
  - `tests/unit/test_memory_epochs.py`
  - `tests/unit/test_voice_vad.py`
  - `tests/unit/test_reflection_prompts.py`
- Modified test files:
  - `tests/unit/test_orchestrator_confirmation.py`
  - `tests/unit/test_orchestrator_artifact_accumulation.py`
  - `tests/unit/test_orchestrator_errors.py`
  - `tests/unit/test_orchestrator_concurrent_tools.py`
  - `tests/e2e/conftest.py`

## Acceptance

- `pytest tests/unit/test_platform_runners.py tests/unit/test_memory_epochs.py tests/unit/test_voice_vad.py tests/unit/test_reflection_prompts.py -q` all green.
- `pytest tests/unit/test_orchestrator*.py -q` green.
- `pytest tests/e2e/ -q` green.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/ tests/` remains at baseline.
- `.kimi-done` includes `LOOP=L51`.

## Handoff

- Write `docs/handoffs/L51-missing-test-coverage-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item.
