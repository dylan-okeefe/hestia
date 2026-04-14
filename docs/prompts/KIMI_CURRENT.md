# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-13 (**L10 Matrix + real-world tests + runtime testing flow**)

---

## Current task

**Active loop:** **L10** — [`../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md`](../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md)

**Kimi prompt (copy or point Kimi at):** [`KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md`](KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md)

**Branch:** `feature/l10-matrix-realworld-runtime` from **`develop`**.

**Goals (summary):**

1. Fix orchestrator **`DONE` → `FAILED`** illegal transition when delivery fails after a successful model completion (Matrix/Telegram).
2. Matrix operator polish: env-based secrets for runtime configs, delivery robustness, docs.
3. Real-world / integration tests (optional env-gated Matrix smoke) + short manual checklist.
4. Document **runtime worktree** flow for testing feature branches without clobbering stable **`~/Hestia-runtime`**.

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration contract: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop audit trail: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- CLI: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
