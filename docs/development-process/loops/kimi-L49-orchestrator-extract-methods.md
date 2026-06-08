# L49 — Orchestrator extract-method pass

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l49-orchestrator-extract-methods` (from `develop`)

## Goal

Decompose `Orchestrator.process_turn` (390 lines, ~lines 160–549) into
readable, testable methods.

## Scope

1. **Extract `_run_inference_loop()`**
   - Lines ~283–404: the model-inference loop (build context → chat → tool dispatch → iterate).
   - Takes: session, turn, context, respond_callback, system_prompt, platform, platform_user.
   - Returns: final content string, or raises for error routing.

2. **Extract `_finalize_turn()`**
   - Lines ~498–548: save slot, record trace, cleanup.
   - Handles both success and failure paths.

3. **Extract `_record_failure_if_enabled()`**
   - Consolidate the two duplicate failure-recording blocks (lines ~436–452 and ~479–496).
   - Takes: turn, error, kind.

4. **Add `IllegalTransitionError` guards**
   - Wrap each `_transition()` call in a try/except that logs the illegal state and fails fast.
   - Currently called in ~7 places; all should surface state bugs explicitly.

5. **Error routing cleanup**
   - `process_turn` should have error routing at the outer level only.
   - Inner methods raise typed exceptions; outer catches and routes.

## Tests

- Targeted unit tests for each extracted method:
  - `_run_inference_loop`: happy path, tool call loop, max iterations.
  - `_finalize_turn`: success saves slot, failure records trace.
  - `_record_failure_if_enabled`: called exactly once per failure.
- Existing orchestrator tests must still pass.
- Add `assert_called_once()` on `inference.chat()` in happy-path tests.

## Acceptance

- `process_turn` is under 100 lines.
- No nested try/except blocks deeper than 2 levels.
- `pytest tests/unit/test_orchestrator*.py -q` green.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline.
- `.kimi-done` includes `LOOP=L49`.

## Handoff

- Write `docs/handoffs/L49-orchestrator-extract-methods-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item.

## Dependencies

- L51 (test coverage bundle) should land first or concurrently so extracted
  methods have test targets.
