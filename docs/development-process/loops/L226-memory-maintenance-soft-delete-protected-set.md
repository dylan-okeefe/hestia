# L226 — Memory Maintenance: Soft-Delete + Protected Set

**Goal:** Add the storage foundation for memory maintenance: soft-delete with retention window and protected-set flags so that later loops can merge/prune/supersede without losing data.

**Branch:** `feature/l226-memory-soft-delete-protected`

## §1 — Schema

Files: `src/hestia/memory/store.py`

Update the `memory` table creation and migration path in `MemoryStore.create_table()`:

- Add columns:
  - `is_active` INTEGER NOT NULL DEFAULT 1
  - `deleted_at` TEXT (ISO datetime, nullable)
  - `deleted_reason` TEXT (nullable)
  - `superseded_by` TEXT (nullable memory id)
  - `is_pinned` INTEGER NOT NULL DEFAULT 0
  - `is_user_authored` INTEGER NOT NULL DEFAULT 0
  - `last_recalled_at` TEXT (ISO datetime, nullable)

- Update `_create_fts5_table` and `_create_regular_table` DDL to include the new columns.
- Keep the existing migration path working: when migrating from the old schema (no platform/platform_user), also default the new columns.
- Add a runtime schema check that selects the new columns.

## §2 — Memory dataclass

File: `src/hestia/memory/store.py`

Extend the `Memory` dataclass with the same new fields. Update `_row_to_memory` to populate them.

## §3 — Store methods

File: `src/hestia/memory/store.py`

Add methods:

- `async def soft_delete(self, memory_id, *, platform=None, platform_user=None, reason="pruned", superseded_by=None) -> bool` — marks inactive, sets `deleted_at`, `deleted_reason`, `superseded_by`. Returns True if found.
- `async def restore(self, memory_id, *, platform=None, platform_user=None) -> bool` — clears inactive/deleted flags.
- `async def pin(self, memory_id, pinned=True) -> bool`
- `async def mark_user_authored(self, memory_id) -> bool`
- `async def mark_recalled(self, memory_id) -> bool` — sets `last_recalled_at` to now.
- `async def list_active_memories(...)` — same signature as `list_memories` but only returns `is_active=1` rows.
- `async def list_inactive_memories(...)` — returns soft-deleted rows within retention.

Update `list_memories` and `search` to only return active rows by default (this is the behavior change consumers expect). Add an optional `include_inactive=False` parameter to both if needed by admin/review UIs later; for this loop the default is active-only.

## §4 — Protected set helper

File: `src/hestia/memory/store.py`

Add a private helper `_is_protected(self, memory: Memory) -> bool` that returns True when any of:

- `is_user_authored` is true
- `is_pinned` is true
- `last_recalled_at` is within the last N days (configurable; default 7)

Expose `is_protected(memory)` as a public method on `MemoryStore` so maintenance loops can use it.

## §5 — Config

File: `src/hestia/config.py`

Add a `[memory.maintenance]` section (or extend `MemoryConfig`) with:

- `retention_days: int = 30` — how long soft-deleted memories are kept before hard-delete.
- `recently_recalled_days: int = 7` — protection window for recently-recalled memories.

These fields are read in this loop via defaults in `MemoryStore`; later loops will wire them through `AppContext`.

## §6 — Tests

File: `tests/unit/memory/test_memory_store.py` (create if missing; extend existing)

- `test_soft_delete_marks_inactive_and_search_excludes_it`
- `test_restore_brings_memory_back`
- `test_protected_set_flags_block_soft_delete` (pin, user-authored, recent recall)
- `test_list_active_and_inactive`
- `test_pin_user_authored_and_recalled_helpers`

## Quality Gates

```bash
uv run pytest tests/unit/memory/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff

Write `docs/handoffs/L226-memory-soft-delete-protected-handoff.md` and update `docs/development-process/kimi-loop-log.md`.

## Critical Rules
- No hard deletes introduced in this loop.
- Default list/search behavior must remain active-only.
- All new columns need both FTS5 and regular-table DDL paths.
