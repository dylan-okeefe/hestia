# LL97 — Config Cli Readability Handoff

**Status:** Complete
**Branch:** `feature/lL97-config-cli-readability`

## Summary

Added `CoreConfig`/`PlatformConfig`/`FeatureConfig` groupings and CLI section separators.

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — passed
- `mypy src/hestia` — clean on changed files
- `ruff check src/ tests/` — clean on changed files

## Notes

No blockers. Ready for merge to develop.
