# L188 — Error Persistence Backend

**Status:** Spec only  
**Branch:** `feature/l188-error-persistence-backend` (from `develop`)  
**Depends on:** L178 (error dashboard)

## Intent

The error dashboard currently tracks resolved/ignored status in module-level Python sets (`_resolved_ids`, `_ignored_ids`). This state evaporates on every server restart — a poor UX where resolved errors flood back in.

This loop moves resolution tracking to SQLite, persists it across restarts, and fixes the arbitrary eviction logic.

## Scope

### §0 — Schema: add `error_resolutions` table

**Why:** We need a place to persist which errors are resolved/ignored.

**In a new Alembic migration:**

```python
op.create_table(
    'error_resolutions',
    sa.Column('error_id', sa.String(), primary_key=True),
    sa.Column('status', sa.String(), nullable=False),  # 'resolved' | 'ignored'
    sa.Column('resolved_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('resolved_by', sa.String(), nullable=True),
)
```

**Commit:** `feat(db): add error_resolutions table`

---

### §1 — Store: create ErrorResolutionStore

**Why:** A dedicated store keeps SQL out of the route layer.

**In `src/hestia/persistence/error_resolution_store.py`:**

```python
class ErrorResolutionStore:
    async def get_status(self, error_id: str) -> str | None: ...
    async def set_status(self, error_id: str, status: str, resolved_by: str | None = None) -> None: ...
    async def list_statuses(self, error_ids: list[str]) -> dict[str, str]: ...
    async def clear_old(self, days: int = 30) -> int: ...  # returns count deleted
```

- `get_status` returns `'resolved'`, `'ignored'`, or `None`
- `set_status` inserts or replaces
- `list_statuses` batches lookups (avoid N+1 in dashboard aggregation)
- `clear_old` removes entries older than N days (replaces the arbitrary 10K cap)

**Commit:** `feat(persistence): add ErrorResolutionStore`

---

### §2 — Routes: wire persistence into error dashboard

**Why:** Replace in-memory sets with DB calls.

**In `src/hestia/web/routes/errors.py`:**

- Replace `_resolved_ids` and `_ignored_ids` module-level sets with `ErrorResolutionStore` calls
- On `POST /errors/{id}/resolve` → `store.set_status(error_id, 'resolved', current_user_id)`
- On `POST /errors/{id}/ignore` → `store.set_status(error_id, 'ignored', current_user_id)`
- On `list_errors` → batch-fetch statuses for all visible errors via `store.list_statuses()`
- Remove `_MAX_RESOLVED` and `set.pop()` eviction — the store's `clear_old()` handles growth
- Keep in-memory caching if desired (e.g., an LRU cache in front of the store), but the source of truth is SQLite

**Commit:** `feat(web): persist error resolutions to SQLite`

---

### §3 — Startup: add cleanup task

**Why:** Prevent the table from growing unbounded.

**In `src/hestia/scheduler/cleanup.py` (or create a lightweight cleanup routine):**

- Add a scheduled task that calls `ErrorResolutionStore.clear_old(days=30)` weekly
- Or run it at scheduler startup if no scheduled task infra exists yet

**Commit:** `feat(scheduler): add error resolution cleanup task`

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

All three must pass.

## Handoff

- Verify resolved errors stay resolved after server restart
- Verify the dashboard still loads quickly (batch lookups, not N+1)
- Verify old resolutions are cleaned up after 30 days
