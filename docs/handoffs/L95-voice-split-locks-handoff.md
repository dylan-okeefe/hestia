# LL95 — Voice Split Locks Handoff

**Status:** Complete
**Branch:** `feature/lL95-voice-split-locks`

## Summary

Split single STT/TTS init lock into two independent locks for concurrent loading.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
