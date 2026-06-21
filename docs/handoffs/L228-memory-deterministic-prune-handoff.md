# L228 — Memory Maintenance: Deterministic Prune

**Branch:** `feature/l228-memory-deterministic-prune`
**Status:** Implementation complete; ready for orchestrator validation.

## What changed

- Added deterministic prune engine in `src/hestia/memory/maintenance/prune.py`.
  - `DeterministicPruner` loads active memories for an identity (or all active memories when no identity is given) and skips the protected set.
  - **Junk rule:** content that would be rejected by `MemorySanitizer.sanitize()` is soft-deleted with `reason="junk"`.
  - **Orphan rule:** memories with a NULL `platform`, NULL `platform_user`, or empty-whitespace content are soft-deleted with `reason="orphan"`.
  - Returns `PruneResult(junk_count, orphan_count)`.
  - Never hard-deletes; only soft-deletes clear junk/orphans.
- Wired `DeterministicPruner` into the maintenance service in `src/hestia/memory/maintenance/service.py`.
  - Added `MemoryMaintenance.run_deterministic_prune(platform=None, platform_user=None)`.
- Updated `src/hestia/memory/maintenance/__init__.py` to export `PruneResult` and `DeterministicPruner`.
- Added unit tests in `tests/unit/memory/maintenance/test_deterministic_prune.py`:
  - Junk memories are soft-deleted.
  - Unscoped memories are soft-deleted.
  - Valid old facts survive the pass.
  - Protected junk memories are preserved.
  - Pruning respects identity scope.

## Quality gates

- `uv run pytest tests/unit/memory/ -q`: **50 passed**
- `uv run mypy src/hestia`: **0 errors**
- `uv run ruff check src/hestia/memory/maintenance tests/unit/memory/maintenance`: **clean**
- Full `uv run ruff check src/ tests/` still reports pre-existing issues in unrelated files; no new issues introduced by L228 files.

## Critical rules observed

- Conservative: only clear junk and unscoped/orphaned memories are removed.
- Soft-delete only; no unattended hard-deletes.
- Protected memories are never pruned.

## Notes for next step

- L229 (LLM near-duplicate merge) and L230 (contradiction/supersession) can continue using the maintenance service as the entry point.
- `docs/development-process/prompts/KIMI_CURRENT.md` should be advanced to L229 by the orchestrator after validation.
