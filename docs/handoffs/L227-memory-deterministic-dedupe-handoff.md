# L227 — Memory Maintenance: Deterministic Dedupe

**Branch:** `feature/l227-memory-deterministic-dedupe`
**Status:** Implementation complete; ready for orchestrator validation.

## What changed

- Added `MemoryStore.update(memory_id, *, content, tags, platform, platform_user)` in `src/hestia/memory/store.py`.
  - Mutates content and/or tags of an active memory in place.
  - Rejects updates that fail the existing `MemorySanitizer` rules.
  - Scopes the update by identity when platform/platform_user are provided.
- Added deterministic dedupe engine in `src/hestia/memory/maintenance/dedupe.py`.
  - `DeterministicDeduper` loads active memories for an identity, skips the protected set, and runs two phases:
    1. **Exact duplicate grouping** by normalized content hash (lowercase, strip whitespace, collapse spaces).
    2. **FTS overlap pairs** using a sanitized excerpt search, then Jaccard word-overlap > 0.8.
  - Merge action:
    - Winner selected by newest `created_at`, then longest content, then lower id.
    - Winner content is rebuilt by deduplicating normalized lines and preserving order.
    - Winner tags are the ordered union of both tag sets.
    - Winner is updated in place via `MemoryStore.update`.
    - Loser is soft-deleted with `reason="deduplicated"` and `superseded_by` pointing to the winner.
  - Returns `DedupeResult(merged_count, skipped_protected_count)`.
- Added maintenance service stub in `src/hestia/memory/maintenance/service.py`.
  - `MemoryMaintenance.run_deterministic_dedupe(platform, platform_user)` delegates to `DeterministicDeduper`.
  - Gives later loops a stable entry point for scheduled maintenance.
- Added package `__init__.py` exporting `DedupeResult`, `DeterministicDeduper`, and `MemoryMaintenance`.
- Added unit tests in `tests/unit/memory/maintenance/test_deterministic_dedupe.py`:
  - Exact duplicates are merged.
  - High-overlap FTS duplicates are merged.
  - Protected memories are skipped.
  - Non-duplicates are left alone.
  - Merge picks the newer memory and unions tags.

## Quality gates

- `uv run pytest tests/unit/memory/ -q`: **45 passed**
- `uv run mypy src/hestia`: **0 errors**
- `uv run ruff check src/hestia/memory/maintenance tests/unit/memory/maintenance`: **clean**
- Full `uv run ruff check src/ tests/` still reports pre-existing issues in unrelated files; no new issues introduced by L227 files.

## Critical rules observed

- No hard-deletes; losers are always soft-deleted with a reason and `superseded_by` reference.
- Protected memories are never merged or deleted.
- Winners are updated in place; only losers are soft-deleted.

## Notes for next step

- L228 (deterministic prune), L229 (LLM near-duplicate merge), and L230 (contradiction/supersession) can build on this maintenance foundation.
- `docs/development-process/prompts/KIMI_CURRENT.md` should be advanced to L228 by the orchestrator after validation.
