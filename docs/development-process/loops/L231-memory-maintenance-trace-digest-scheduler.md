# L231 — Memory Maintenance: Trace, Digest, and Scheduler Wiring

**Goal:** Record every maintenance action in a trace, emit a periodic operator digest reusing the blocked-actions digest surface, and wire the two maintenance cadences into the scheduler.

**Branch:** `feature/l231-memory-maintenance-trace-digest-scheduler`

## §0 — Depends on

Merge `feature/l230-memory-contradiction-supersession` into `develop` first.

## §1 — Maintenance trace store

Create `src/hestia/memory/maintenance/trace.py` and integrate with persistence.

`MaintenanceAction` dataclass:

- `id: str`
- `action: str` — "merge", "prune", "supersede"
- `identity_platform: str | None`
- `identity_user: str | None`
- `winner_memory_id: str | None`
- `loser_memory_ids: list[str]`
- `reason: str`
- `created_at: datetime`
- `undoable_until: datetime` — now + retention_days
- `details: dict[str, Any]` — extra context such as confidence, attribute, merged content

Create `src/hestia/persistence/maintenance_trace_store.py`:

- `create_table()` — regular SQLite table (not FTS).
- `record(action)` — persist a MaintenanceAction.
- `list_recent(platform=None, platform_user=None, since=None, limit=100)` — for digests and review.
- `get(action_id)` — for undo lookup.

Update `src/hestia/persistence/db.py` `create_tables()` or bootstrap to call this.

## §2 — Wire trace into engines

Files: `src/hestia/memory/maintenance/dedupe.py`, `prune.py`, `llm_dedupe.py`, `contradictions.py`

Accept an optional `trace_store: MaintenanceTraceStore` in each engine constructor. After every merge/prune/supersede, call `trace_store.record(...)` with full details. If no trace_store is provided, log at INFO level instead.

## §3 — Digest

Create `src/hestia/memory/maintenance/digest.py`.

Class `MemoryMaintenanceDigest`:

- `__init__(trace_store: MaintenanceTraceStore, session_store: SessionStore | None = None, notifier: PlatformNotifier | None = None)`
- `async def send_digest(since=None, session_id=None, title="Memory maintenance digest") -> str`
- Formats:
  - Total actions
  - Merges
  - Prunes
  - Supersessions (prominently highlighted)
  - Undo deadline
- Returns `"SILENT"` if no actions.
- Optional `_notify` to push to operator if notifier + session are configured.

## §4 — Scheduler wiring

Files: `src/hestia/scheduler/engine.py`, `src/hestia/app.py`

- Add `task_type == "memory_maintenance_deterministic"` to `_fire_task` in `Scheduler`.
- Add `task_type == "memory_maintenance_llm"` to `_fire_task`.
- For deterministic task: call `app.memory_maintenance.run_deterministic_pass(platform, platform_user)` and then `app.memory_maintenance_digest.send_digest_for_task(task)`.
- For LLM task: call `app.memory_maintenance.run_llm_pass(platform, platform_user)` and then digest.

Add helpers in `src/hestia/memory/maintenance/service.py`:

- `async def run_deterministic_pass(platform, platform_user)` — runs dedupe + prune.
- `async def run_llm_pass(platform, platform_user)` — runs LLM dedupe + contradiction resolution.

Add `ensure_memory_maintenance_tasks` helper in `src/hestia/memory/maintenance/scheduler.py` (create) to register:

- Deterministic task: nightly cron, e.g. `"0 3 * * *`.
- LLM task: weekly cron, e.g. `"0 4 * * 0`.

Make times/frequencies configurable in `config.memory.maintenance`.

Wire in `AppContext.bootstrap_db()` or a CLI command to ensure tasks exist for the system session.

## §5 — AppContext wiring

File: `src/hestia/app.py`

- Add `memory_maintenance` cached property.
- Add `memory_maintenance_digest` cached property.
- Inject both into `Scheduler` construction.

## §6 — Tests

Files:
- `tests/unit/memory/maintenance/test_trace.py`
- `tests/unit/memory/maintenance/test_digest.py`
- `tests/unit/scheduler/test_memory_maintenance_tasks.py` (create or extend existing scheduler tests)

Tests:
- `test_merge_records_trace`
- `test_prune_records_trace`
- `test_supersede_records_trace_with_reasoning`
- `test_digest_formats_supersessions_prominently`
- `test_digest_returns_silent_when_no_actions`
- `test_scheduler_runs_deterministic_task`
- `test_scheduler_runs_llm_task`

## §7 — Undo command (optional but recommended)

File: `src/hestia/cli.py` or `src/hestia/memory/maintenance/undo.py`

Add an async function `undo_maintenance_action(action_id)` that:

- Looks up the action in the trace store.
- Restores all `loser_memory_ids` via `MemoryStore.restore()`.
- Records an "undo" trace entry.

Expose via CLI subcommand if one exists for maintenance; otherwise add a TODO and defer.

## Quality Gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff

Write `docs/handoffs/L231-memory-trace-digest-scheduler-handoff.md` and update `docs/development-process/kimi-loop-log.md`.

## Critical Rules
- Every merge/prune/supersede must be traced.
- Supersessions must be front-and-center in the digest.
- Scheduler tasks must be idempotent: calling ensure twice updates rather than duplicates.
