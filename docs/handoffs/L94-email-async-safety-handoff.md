# LL94 — Email Async Safety Handoff

**Status:** Complete
**Branch:** `feature/lL94-email-async-safety`

## Summary

Wrapped blocking IMAP calls in `asyncio.to_thread` for async safety.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
