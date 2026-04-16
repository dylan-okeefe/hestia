# Kimi loop L02 — Phase 8a (identity + reasoning budget)

**Branch:** `feature/phase-8a-identity-reasoning` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§8.1** — Compiled identity view (SOUL.md), `IdentityConfig`, compiler, context builder integration, tests, **ADR-022**.

- **§8.2** — Wire `reasoning_budget` through `PolicyEngine` and orchestrator (replace hardcoded `2048`).

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/development-process/kimi-loops/L02-phase-8a-identity-reasoning.md
BRANCH=feature/phase-8a-identity-reasoning
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
