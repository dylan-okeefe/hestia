# L52 ContextBuilder Decomposition — Handoff

## Scope

Decomposed `ContextBuilder.build` (was ~215 lines) into two dedicated
components:

- **`HistoryWindowSelector`** — encapsulates history truncation/selection logic
- **`CompressedSummaryStrategy`** — encapsulates compression retry/splicing logic

Thinned `ContextBuilder.build` to 78 lines (under the 80-line target).

## Files changed

| File | Change |
|------|--------|
| `src/hestia/context/history_window_selector.py` | **New.** `HistoryWindowSelector` with `select(history, budget, token_counter, skip_message)` — walks history newest-first, keeps tool pairs intact, returns `(included, dropped, truncated_count)` in chronological order |
| `src/hestia/context/compressed_summary_strategy.py` | **New.** `CompressedSummaryStrategy` with `try_splice(dropped_history, protected_top, protected_bottom, included_history, budget, count_messages)` — generates summary, tries insertion after system message, retries once by dropping oldest included message |
| `src/hestia/context/builder.py` | Refactored `build()` to 78 lines. Imports and delegates to the two new classes. Preserves all existing behavior: tokenize cache, join-overhead cache, prefix layers, calibration correction, protected message handling |
| `tests/unit/test_history_window_selector.py` | **New.** Coverage: empty history, exact budget fit, single message over budget, skip_message, tool pair keep/drop, oldest-first truncation |
| `tests/unit/test_compressed_summary_strategy.py` | **New.** Coverage: happy path summary insertion, empty summary fallback, retry drops oldest message, fallback when retry also fails, no-included-history fallback |

## Design decisions

1. **Token counter as async callable** — `HistoryWindowSelector` receives
   `token_counter: Callable[[Message], Awaitable[int]]` so tests can inject a
   mock without needing a real tokenizer. The caller (`ContextBuilder`) passes
   a closure that adds join overhead to `_count_tokens`.

2. **Chronological order return** — Both `included` and `dropped` are returned
   in chronological order (oldest first). This is cleaner than the original
   internal convention where `dropped_history` was reverse-chronological and
   reversed before passing to the compressor.

3. **Full-list budget check in compression** — `CompressedSummaryStrategy`
   checks the *full* message list (protected + summary + included + bottom)
   against budget on both the initial attempt and the retry. The original code
   only checked `protected_top + summary_msg` on the first attempt, which could
   silently exceed budget after adding history back.

4. **No change to `BuildResult` or public API** — `ContextBuilder.build`
   signature, `BuildResult` fields, and `enable_compression` wiring are
   unchanged. Existing callers (orchestrator, CLI, tests) require no updates.

## Final gate

```
Tests:    43 passed (5 context builder existing + 2 new test files)
Mypy:     0 errors in src/hestia/context/
Ruff:     0 errors in src/hestia/context/
build():  78 lines
Branch:   feature/l52-context-builder-decomposition
```

## Issues to carry forward

- The `HistoryWindowSelector` budget math is linear (`running_total + cost <=
  budget`). With `body_factor != 1.0`, the integer-division correction in
  `_apply_correction` can diverge by at most 1 token per message from the
  original total-body correction. All existing tests use `body_factor=1.0`, so
  this is not currently observable. If future loops need exact parity with
  non-1.0 body factors, pass a `budget_checker` callable instead of a scalar
  budget.

- `CompressedSummaryStrategy.try_splice` has a relatively wide signature (7
  parameters). If future loops add more retry strategies (e.g. recursive
  summarization, hierarchical compression), consider extracting a
  `CompressionResult` dataclass to reduce parameter count.
