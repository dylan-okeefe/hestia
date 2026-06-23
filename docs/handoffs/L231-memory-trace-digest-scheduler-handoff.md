# L231 — Memory Maintenance: Trace, Digest, and Scheduler Wiring

**Branch:** `feature/l231-memory-trace-digest-scheduler`
**Status:** Implementation complete; ready for Cursor review / orchestrator validation.

## What changed

- Added `src/hestia/memory/maintenance/trace.py` with the `MaintenanceAction` dataclass.
  - Records `id`, `action` (merge/prune/supersede/undo), identity scope, winner/loser memory ids, reason, timestamps, undo deadline, and free-form details.
- Added `src/hestia/persistence/maintenance_trace_store.py` with `MaintenanceTraceStore`.
  - `create_table()` creates the `maintenance_trace` table and supporting indexes idempotently.
  - `record(action)` persists a `MaintenanceAction`.
  - `list_recent(...)` queries by identity and time window for digests and review.
  - `get(action_id)` supports undo lookup.
- Added the `maintenance_trace` table to `src/hestia/persistence/schema.py` so `Database.create_tables()` creates it automatically.
- Wired tracing into all four maintenance engines:
  - `src/hestia/memory/maintenance/dedupe.py`
  - `src/hestia/memory/maintenance/prune.py`
  - `src/hestia/memory/maintenance/llm_dedupe.py`
  - `src/hestia/memory/maintenance/contradictions.py`
  - Each accepts an optional `trace_store`; when absent it logs at INFO instead.
  - All engines now read `undo_retention_days` from `MemoryMaintenanceConfig`.
- Added `src/hestia/memory/maintenance/digest.py` with `MemoryMaintenanceDigest`.
  - `send_digest(...)` returns `"SILENT"` when no actions occurred in the window.
  - Formats total actions, merges (grouped by phase), prunes (grouped by reason), and prominently highlights supersessions at the top.
  - Reports the soonest undo deadline.
  - Optional `_notify` path pushes the digest to the operator when a notifier + session are configured.
- Added `src/hestia/memory/maintenance/scheduler.py` with `ensure_memory_maintenance_tasks`.
  - Creates/updates a deterministic nightly cron task (`memory_maintenance_deterministic`) and a weekly LLM task (`memory_maintenance_llm`).
  - Calling twice for the same identity updates the existing tasks instead of duplicating them.
  - Cron expressions default to `0 3 * * *` and `0 4 * * 0` and are configurable via `config.memory.maintenance`.
- Extended `MemoryMaintenance` in `src/hestia/memory/maintenance/service.py` with `run_deterministic_pass` and `run_llm_pass` entry points.
- Wired the scheduler in `src/hestia/scheduler/engine.py` to fire both maintenance task types, run the appropriate pass, and deliver the digest.
- Wired `AppContext` in `src/hestia/app.py`:
  - `memory_maintenance` cached property.
  - `memory_maintenance_digest` cached property.
  - `memory_maintenance_undo` cached property.
  - `ensure_memory_maintenance_tasks(platform, platform_user)` helper.
  - `bootstrap_db()` creates the maintenance trace table.
- Wired both maintenance services into all `Scheduler` constructors:
  - `src/hestia/commands/scheduler.py` (run + daemon)
  - `src/hestia/platforms/runners.py` (Telegram/Matrix runners)
- Added undo support:
  - `src/hestia/memory/maintenance/undo.py` with `MaintenanceUndo.undo(action_id)`.
  - Restores all `loser_memory_ids` via `MemoryStore.restore()` and records an "undo" trace entry.
  - Rejects undos outside the undo window or on undo actions themselves.
  - Added `hestia memory maintenance undo <action-id>` CLI command in `src/hestia/cli.py`.
- Added unit tests:
  - `tests/unit/memory/maintenance/test_trace.py` — merge, prune, supersede, LLM dedupe, and undo trace recording.
  - `tests/unit/memory/maintenance/test_maintenance_digest.py` — supersession prominence, silent empty window, undo deadline, and `since` window filtering.
  - `tests/unit/scheduler/test_memory_maintenance_tasks.py` — deterministic and LLM scheduler task routing, SILENT delivery, and missing-service error handling.

## Quality gates

- `uv run pytest tests/unit/memory/maintenance/test_trace.py tests/unit/memory/maintenance/test_maintenance_digest.py tests/unit/scheduler/test_memory_maintenance_tasks.py -q`: **13 passed**
- `uv run pytest tests/unit/ tests/integration/ -q`: **1719 passed, 1 failed** (failure is `tests/unit/tools/test_browser_ssrf.py::test_fetch_url_allows_public_url`, unrelated to L231).
- `uv run mypy src/hestia`: **0 errors**
- `uv run ruff check` on changed source files: **clean**
- Full-repo `uv run ruff check src/ tests/` still reports pre-existing issues in unrelated files; no new issues introduced by L231.

## Notes for next step

- The orchestrator/Cursor should advance `docs/development-process/prompts/KIMI_CURRENT.md` to the next loop after validation.
- No merge into `develop` or `feature/memory-maintenance` was performed per instructions.
