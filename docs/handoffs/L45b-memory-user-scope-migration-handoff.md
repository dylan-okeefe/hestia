# L45b — Memory user-scope migration

**Status:** Complete on feature branch; not merged to `develop` (post-release merge discipline).

**Branch:** `feature/l45b-memory-user-scope-migration`

**Implementation commit:** `6ea59ed`

---

## What shipped

### MemoryStore user scoping (`src/hestia/memory/store.py`)

- `Memory` dataclass gained `platform` and `platform_user` fields (both `str | None`, default `None`).
- `MemoryStore.create_table()` now:
  - Detects FTS5 availability at runtime (probes with `_fts5_probe` virtual table).
  - Migrates old-schema FTS5 tables (without `platform`/`platform_user`) by backing up data, dropping the old virtual table, recreating with the new schema, and restoring with `NULL` for the new columns.
  - Falls back to a regular SQLite table with indexes when FTS5 is unavailable.
- All query methods (`save`, `search`, `list_memories`, `delete`, `count`) accept optional `platform`/`platform_user` parameters and fall back to runtime `ContextVars` (`current_platform`, `current_platform_user`) when not provided.
- Cross-user access is blocked by default: when a user identity is present, queries filter to that identity.

### LIKE fallback (`src/hestia/memory/store.py`)

- When FTS5 is unavailable, `search()` uses `content LIKE '%query%'`.
- `list_memories()` tag filtering uses exact-tag matching via multiple `LIKE` patterns (`tag %`, `% tag %`, `% tag`) to avoid false positives on partial tokens.

### Memory tools (`src/hestia/tools/builtin/memory_tools.py`)

- `save_memory` explicitly reads `current_platform` and `current_platform_user` from runtime ContextVars and passes them to `MemoryStore.save()`.
- `search_memory` and `list_memories` rely on the store's ContextVar fallback (comments added for clarity).

### Epoch user scoping (`src/hestia/memory/epochs.py`)

- `MemoryEpochCompiler.compile(session)` now passes `session.platform` and `session.platform_user` to `_fetch_recent_memories()`, which forwards them to `MemoryStore.list_memories()`.
- Epochs are compiled only from memories belonging to the session's user.

### Tests

- **New:** `tests/unit/test_memory_user_scope.py` (15 tests)
  - User-scoped save/search/list/delete/count
  - Cross-user access blocked
  - ContextVar fallback for identity
  - Tool-level ContextVar integration
  - LIKE fallback search and tag filtering
  - Old-schema FTS5 migration with data preservation
- **Updated:** `tests/unit/test_memory_epochs.py` — memories now saved with explicit `platform`/`platform_user` to match the session identity used in compilation.
- **Updated:** `tests/integration/test_memory_matrix_mock.py` — pre-seeded memories now include `platform="test"`, `platform_user="user"` to align with the `_make_session` identity.

---

## Gates

| Gate | Result |
|------|--------|
| `pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q` | **820 passed, 6 skipped** |
| `mypy src/hestia` | **0 errors** |
| `ruff check src/` | **23 errors** (baseline unchanged) |

---

## Queued next

- **L45c** — Multi-user docs and hardening (`docs/development-process/kimi-loops/L45c-multi-user-docs-and-hardening.md`)

## Reference

- Loop spec: `docs/development-process/kimi-loops/L45b-memory-user-scope-migration.md`
- Feature branch: `feature/l45b-memory-user-scope-migration`
