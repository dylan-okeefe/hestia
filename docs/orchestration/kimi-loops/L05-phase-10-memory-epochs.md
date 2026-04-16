# Kimi loop L05 — Phase 10 (memory epochs)

## Review carry-forward

- **Test baseline:** **`379 passed`** on `develop` after L04 merge — keep `uv run pytest tests/unit/ tests/integration/ -q` green.
- **E2E:** `tests/e2e/` Matrix harness is **skipped by default** (`pytestmark` in `test_basic_roundtrip.py`); do not pull those into the default unit/integration job without opt-in markers.
- **Context builder** already accepts compiled **identity** prefix (L02); memory epoch text should compose **after** identity and **before** base system prompt per roadmap §10.1 ordering — avoid duplicating memory content every `save_memory` mid-session.
- **Migrations:** If new tables/columns for epochs or FTS, add Alembic revision consistent with `schema.py`.

**Branch:** `feature/phase-10-memory-epochs` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§10.1** — `MemoryEpoch`, `MemoryEpochCompiler`, context builder + CLI integration, refresh rules, **ADR-023**.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L05-phase-10-memory-epochs.md
BRANCH=feature/phase-10-memory-epochs
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
