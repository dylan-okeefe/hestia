# Kimi loop L08 — Phase 13 (security audit CLI)

## Review carry-forward

- **Test baseline:** update after L07 merge (expect **>** 386 once skills land).
- **`hestia audit` trace checks (§13.1):** `TraceStore` / `traces` table may be **empty** on fresh DB — implement checks that **no-op or report “no traces”** instead of erroring.
- **`hestia policy show` (§13.2):** Must reflect **capability** and **reasoning_budget** wiring post–L02/L03 (policy engine + `CliAppContext`).

**Branch:** `feature/phase-13-audit` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§13.1** — `hestia audit` deterministic checks (as listed; note trace-based checks require Phase 11 traces — implement guards if traces missing).
- **§13.2** — `hestia policy show`.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L08-phase-13-audit.md
BRANCH=feature/phase-13-audit
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
