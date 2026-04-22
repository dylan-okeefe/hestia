# L52 — ContextBuilder decomposition

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l52-context-builder-decomposition` (from `develop`)

## Goal

Decompose `ContextBuilder.build` (lines 215–429) so token accounting is
separated from history selection and compression retry logic.

## Scope

1. **Extract `HistoryWindowSelector`**
   - `select(history: list[Message], budget: int) -> list[Message]`
   - Encapsulates the truncation/selection logic (lines ~304–369).
   - Must not need a real tokenizer — accept a token-count callable.

2. **Extract `CompressedSummaryStrategy`**
   - `summarize(history: list[Message], budget: int) -> str`
   - Encapsulates the compression retry logic (lines ~375–411).
   - Reuses the existing `HistoryCompressor` or replaces it.

3. **Thin `ContextBuilder.build`**
   - Build context becomes: assemble system prompt → select history window → if overflow, compress → return `BuiltContext`.
   - No nested retry loops inside `build`.

4. **Targeted unit tests**
   - `HistoryWindowSelector` with a mock tokenizer.
   - `CompressedSummaryStrategy` with a mock inference.
   - Edge cases: empty history, exact budget fit, single message over budget.

## Tests

- New test files:
  - `tests/unit/test_history_window_selector.py`
  - `tests/unit/test_compressed_summary_strategy.py`
- Existing `tests/unit/test_context_builder_compression.py` and related tests must still pass.

## Acceptance

- `ContextBuilder.build` is under 80 lines.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline.
- `pytest tests/unit/test_context_builder*.py -q` green.
- `.kimi-done` includes `LOOP=L52`.

## Handoff

- Write `docs/handoffs/L52-context-builder-decomposition-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item.

## Dependencies

- L51 (test coverage) should land first so new components have a test harness.
- L49 (orchestrator extract) can land before or after; no direct coupling.
