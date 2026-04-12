# Kimi loop L05 — Phase 10 (memory epochs)

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
