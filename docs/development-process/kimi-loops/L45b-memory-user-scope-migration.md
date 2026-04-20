# L45b — Memory user-scope migration

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l45b-memory-user-scope-migration` (from `develop`)

## Goal

Migrate memory storage to FTS5 and scope memory queries, tools, and epochs
to the user identity (`platform:platform_user`) established in L45a.

## Scope

1. **FTS5 memory migration**
   - Add FTS5 virtual table for memory content search.
   - Backfill existing memory rows into FTS5 index.
   - Fall back to LIKE search on SQLite builds without FTS5.

2. **User-scoped memory queries**
   - Update `memory/store.py` queries to filter by `platform:platform_user`
     via the runtime ContextVars set in L45a.
   - Default behavior: scope to current user; admin/owner override configurable.

3. **User-scoped memory tools**
   - `search_memory` and `save_memory` tools should respect user scope.
   - Tool metadata indicates `requires_confirmation` for cross-user memory access.

4. **Epoch user scoping**
   - `MemoryEpoch` records tagged with creator identity.
   - Epoch rebuild respects user boundaries.

## Tests

- New unit tests:
  - FTS5 index creation and query parity with LIKE fallback
  - Memory tools scoped to current user via ContextVar
  - Cross-user memory access blocked without explicit override
- Keep existing tests green.

## Acceptance

- `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q` green.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline or better.
- `.kimi-done` includes `LOOP=L45b`.

## Handoff

- Write `docs/handoffs/L45b-memory-user-scope-migration-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to L45c.
