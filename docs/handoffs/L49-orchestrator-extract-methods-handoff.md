# L49 — Orchestrator extract-methods handoff

**Status:** complete
**Branch:** `feature/l49-orchestrator-extract-methods`
**Spec:** [`../development-process/kimi-loops/L49-orchestrator-extract-methods.md`](../development-process/kimi-loops/L49-orchestrator-extract-methods.md)

## What shipped

Pure refactor of `src/hestia/orchestrator/engine.py` (`process_turn` ~390 lines → 98 lines) with zero behavior change.

| Extracted method | Replaces | Lines |
| --- | --- | --- |
| `_prepare_turn_context(...)` | Session setup, context build, slot acquisition, style prefix, allow-list | ~60 |
| `_run_inference_loop(...)` | Model chat → tool dispatch → iterate loop (was ~120 lines inline) | ~140 |
| `_handle_context_too_large(...)` | Overflow error handler with handoff summarizer | ~40 |
| `_handle_unexpected_error(...)` | Generic exception handler with failure bundle | ~35 |
| `_record_failure_if_enabled(...)` | Duplicated failure-recording blocks in both error handlers | ~20 |
| `_finalize_turn(...)` | Slot save, turn update, trace record, artifact cleanup | ~55 |
| `_safe_transition(...)` | `_transition()` wrapped with `IllegalTransitionError` guard | ~10 |

Additional cleanups:
- `process_turn` now has error routing at the outer level only: `ContextTooLargeError`, `IllegalTransitionError` (re-raised), generic `Exception`.
- `_safe_transition` logs the illegal state and re-raises so state bugs fail fast.
- No changes to `app.py`, `cli.py`, or any caller of `process_turn`.

## Test results

```
19 passed, 0 failed (orchestrator tests)
mypy src/hestia/orchestrator/engine.py: 0 errors
ruff check src/hestia/orchestrator/engine.py: 0 errors
```

Pre-existing mypy/ruff baseline in other files unchanged.

## Commits

1. `refactor(orchestrator): extract methods from process_turn`

## Carry-forward

- `context_builder.build` is called **twice** on tool-call paths (once before inference, once after tool results are appended). This is expected and preserved. Any future loop that tries to add `assert_called_once()` to `build` in tool-call tests will fail — use `assert_called()` instead.
- `engine.py` is still 900+ lines total; the remaining bulk is in `_execute_tool_calls`, `_dispatch_tool_call`, `_execute_policy_delegation`, and `_check_confirmation`. These are already extracted as methods from prior loops (L31, L40) and are individually under 100 lines.
- The `aiosqlite` `RuntimeError: Event loop is closed` warning during test teardown is pre-existing and unrelated.
