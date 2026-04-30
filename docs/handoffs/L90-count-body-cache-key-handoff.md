# LL90 — Count Body Cache Key Handoff

**Status:** Complete
**Branch:** `feature/lL90-count-body-cache-key`

## Summary

Replaced `_count_body` string-join cache key with hash-based key to prevent collisions.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
