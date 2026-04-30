# LL96 — Audit Strict Doctor Overlap Handoff

**Status:** Complete
**Branch:** `feature/lL96-audit-strict-doctor-overlap`

## Summary

Added `--strict` flag to `hestia audit run` and clarified doctor vs audit help text.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
