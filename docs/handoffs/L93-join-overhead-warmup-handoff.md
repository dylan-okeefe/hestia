# LL93 — Join Overhead Warmup Handoff

**Status:** Complete
**Branch:** `feature/lL93-join-overhead-warmup`

## Summary

Added `ContextBuilder.warm_up()` and called it during startup to eliminate first-turn latency.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
