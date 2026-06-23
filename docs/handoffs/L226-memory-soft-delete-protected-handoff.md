# L226 — Memory Maintenance: Soft-Delete + Protected Set

**Branch:** `feature/l226-memory-soft-delete-protected`
**Status:** Implementation complete; ready for orchestrator validation.

## What changed

- Extended the memory schema in `src/hestia/memory/store.py`:
  - Added `is_active`, `deleted_at`, `deleted_reason`, `superseded_by`, `is_pinned`, `is_user_authored`, and `last_recalled_at` columns to both FTS5 and regular-table DDL.
  - Updated the old-schema migration path (no `platform`/`platform_user`) to default the new columns.
  - Updated the runtime schema check to select the new columns.
- Extended the `Memory` dataclass with the same fields and updated `_row_to_memory` to populate them.
- Added store methods:
  - `soft_delete(memory_id, *, platform, platform_user, reason, superseded_by)` — marks inactive and records deletion metadata.
  - `restore(memory_id, *, platform, platform_user)` — clears inactive/deleted flags.
  - `pin(memory_id, pinned=True)` — toggles the pinned flag.
  - `mark_user_authored(memory_id)` — sets the user-authored flag.
  - `mark_recalled(memory_id)` — sets `last_recalled_at` to now.
  - `list_active_memories(...)` / `list_inactive_memories(...)` — active-only and retention-window listings.
- Changed default behavior:
  - `list_memories` and `search` now return active rows only.
  - Both accept an optional `include_inactive=False` parameter for admin/review paths.
- Added protected-set logic:
  - `_is_protected(memory)` returns True when `is_user_authored`, `is_pinned`, or `last_recalled_at` is within `recently_recalled_days`.
  - Exposed publicly as `MemoryStore.is_protected(memory)`.
- Added maintenance config in `src/hestia/config.py`:
  - `MemoryConfig.retention_days` (default 30).
  - `MemoryConfig.recently_recalled_days` (default 7).
  - `MemoryStore` accepts an optional `MemoryConfig`; defaults are used until later loops wire it through `AppContext`.
- Added unit tests in `tests/unit/memory/test_memory_store.py`:
  - Soft-delete marks inactive and excludes from search/list.
  - Restore brings a memory back.
  - Protected-set flags block soft-delete semantics (pin, user-authored, recent recall).
  - Active/inactive listing and `include_inactive` behavior.
  - Pin/user-authored/recalled helper methods.

## Quality gates

- `uv run pytest tests/unit/memory/ -q`: **40 passed**
- `uv run mypy src/hestia`: **0 errors**
- `uv run ruff check src/hestia/memory/store.py src/hestia/config.py tests/unit/memory/test_memory_store.py`: **clean**
- Full `uv run ruff check src/ tests/` still reports pre-existing issues in unrelated files; no new issues introduced by L226 files.

## Critical rules observed

- No new hard-delete path introduced; `delete()` remains the existing hard-delete escape hatch.
- Default `list_memories`/`search` behavior is active-only.
- All new columns are present in both FTS5 and regular-table DDL paths.

## Notes for next step

- L227 (deterministic dedupe), L228 (deterministic prune), L229 (LLM near-duplicate merge), and L230 (contradiction/supersession) can now build on this storage foundation.
- `docs/development-process/prompts/KIMI_CURRENT.md` should be advanced to L227 by the orchestrator after validation.
