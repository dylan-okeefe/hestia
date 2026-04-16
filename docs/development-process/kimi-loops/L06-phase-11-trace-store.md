# Kimi loop L06 — Phase 11 (trace store + enriched failure bundles)

## Review carry-forward

- **Test baseline:** **`386 passed`** on `develop` after L05 — keep default unit/integration green.
- **Orchestrator `finally`:** Tracing must **never** mask the original exception; use a narrow try/except around trace persistence only, and avoid awaiting inside paths that could recurse into `process_turn`.
- **Alembic:** Match `schema.py`; if `failure_bundles` grows columns, ensure downgrade and fresh `create_tables` dev paths stay coherent with existing Phase 6 failure tests.
- **Memory epochs (L05):** `ContextBuilder` / system message assembly is now multi-part — trace `user_input_summary` should remain stable (first N chars of user message), not the compiled epoch blob.

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
SPEC=docs/development-process/kimi-loops/L06-phase-11-trace-store.md
BRANCH=feature/phase-11-trace-store
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
