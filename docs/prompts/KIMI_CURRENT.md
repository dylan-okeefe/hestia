# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-14 (**L10–L14 chain**)

---

## Current task

**Active loop:** **L10** (first of five) — [`../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md`](../orchestration/kimi-loops/L10-matrix-realworld-runtime-testing.md)

**Full chain (L10→L14):** [`KIMI_LOOPS_L10_L14.md`](KIMI_LOOPS_L10_L14.md) · **Queue:** [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)

**Kimi prompt (L10):** [`KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md`](KIMI_PHASE_15_MATRIX_REALWORLD_PROMPT.md) (adapt `LOOP` / spec link for L11+)

**Branch:** `feature/l10-matrix-realworld-runtime` from **`develop`**.

**L10 scope (only):** orchestrator post-`DONE` delivery error handling; Matrix **env-based** config + adapter send/edit robustness. **Not** in L10: exhaustive mock tests (→ **L11**), live Matrix E2E (→ **L12**), scheduler/cron (→ **L13**), big doc bundle (→ **L14**).

**Dylan — before L12:** collect credentials per [`docs/testing/CREDENTIALS_AND_SECRETS.md`](../testing/CREDENTIALS_AND_SECRETS.md).

---

## Reference

- Orchestration contract: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop audit trail: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- CLI: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
