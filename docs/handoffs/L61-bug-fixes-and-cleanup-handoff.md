# L61 — Bug Fixes and Minor Cleanup

## Scope

Fix four duplicate-definition bugs and three minor code-quality issues.

## Commits

| Commit | Description |
|--------|-------------|
| `e0065ec` | Remove duplicate `_compile_and_set_memory_epoch` from app.py |
| `431d68a` | Move `TransitionCallback` to `orchestrator/types.py` |
| `867655d` | Consolidate `_sanitize_user_error` in `TurnFinalization` |
| `b2044e3` | Add neither-set guard to `ScheduledTask.__post_init__` |
| `037b17f` | Inline `WebSearchError` in `classify_error` mapping |
| `perf(tools)` | Wrap `list_dir` iterdir loop in single `asyncio.to_thread` |

## Files changed

- `src/hestia/app.py` — removed duplicate, updated imports
- `src/hestia/orchestrator/types.py` — added `TransitionCallback`
- `src/hestia/orchestrator/assembly.py` — import from types.py
- `src/hestia/orchestrator/finalization.py` — import from types.py
- `src/hestia/orchestrator/execution.py` — import from types.py
- `src/hestia/orchestrator/engine.py` — import `_sanitize_user_error` from finalization.py
- `src/hestia/core/types.py` — added neither-set guard
- `src/hestia/errors.py` — added `WebSearchError`
- `src/hestia/tools/builtin/web_search.py` — imports from errors.py
- `src/hestia/tools/builtin/list_dir.py` — single `asyncio.to_thread` wrap

## Acceptance

- [x] All four duplicate definitions resolved
- [x] `ScheduledTask` rejects both-None and both-set
- [x] Tests updated for new validation
- [x] `mypy` and `ruff` clean on changed files
