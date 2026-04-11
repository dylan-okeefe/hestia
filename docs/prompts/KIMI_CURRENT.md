# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review. **You:** read this file first in each session, then open the linked prompt and execute it end-to-end.

**Last set by:** Cursor — 2026-04-11 (after Phase 6 closeout review)

---

## Current task (do this now)

1. Ensure you are on **up-to-date `develop`** (`git checkout develop && git pull` if you use a remote).
2. Create branch **`feature/phase-7-matrix`** from `develop`.
3. Open **[`KIMI_PHASE_7_MATRIX.md`](./KIMI_PHASE_7_MATRIX.md)** and implement it fully (adapter, config, CLI, tests, ADR-021 per that file and [`docs/design/matrix-integration.md`](../design/matrix-integration.md)).
4. **Report back:** `git log --oneline -8`, `pytest` summary, and list of new/modified files.

---

## Next task (after Cursor review)

Cursor will add a follow-up prompt here if Matrix review finds gaps; otherwise see [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md) roadmap.

---

## Reference

- Orchestration contract: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
