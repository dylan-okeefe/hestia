# LL98 — Token Batch Handoff

**Status:** Complete
**Branch:** `feature/lL98-token-batch`

## Summary

Added `tokenize_batch` to InferenceClient and wired it into `_count_body` for single-call counting.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
