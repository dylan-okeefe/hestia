# Kimi loop L06 — Phase 11 (trace store + enriched failure bundles)

**Branch:** `feature/phase-11-trace-store` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§11.1** — Trace data model, SQLite `traces` table, `TraceStore`, orchestrator `finally` hook, Alembic migration.
- **§11.2** — Enriched `FailureBundle` fields, migrations, engine integration.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L06-phase-11-trace-store.md
BRANCH=feature/phase-11-trace-store
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
