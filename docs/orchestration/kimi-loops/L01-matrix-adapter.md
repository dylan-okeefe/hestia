# Kimi loop L01 — Matrix platform adapter

**Goal:** Ship the Matrix `Platform` adapter, config, CLI wiring, and tests so automation can target Matrix.

**Base:** Latest `develop` (merge or rebase after Phase 7 cleanup lands if needed).

**Branch:** `feature/matrix-adapter`

**Spec (read end-to-end, implement fully):** [`../../design/matrix-integration.md`](../../design/matrix-integration.md)

**ADR:** Add **ADR-021** as described in that design doc.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push` the feature branch.
3. Handoff notes under `docs/handoffs/` when useful.
4. Write **`.kimi-done`** at repo root (gitignored):

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L01-matrix-adapter.md
BRANCH=feature/matrix-adapter
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

5. Do **not** commit `.kimi-done`.
