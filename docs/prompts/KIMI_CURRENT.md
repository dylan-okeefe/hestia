# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-14 (**L12 merged; L13 active**)

---

## Current task

**Active loop:** **L13** — [`../orchestration/kimi-loops/L13-scheduler-matrix-cron.md`](../orchestration/kimi-loops/L13-scheduler-matrix-cron.md)

**Full chain:** [`KIMI_LOOPS_L10_L14.md`](KIMI_LOOPS_L10_L14.md)

**Branch:** Create **`feature/l13-scheduler-matrix-cron`** from **`develop`** (must include L12 merge).

**Kimi prompt:** Point Kimi at **`KIMI_CURRENT.md`** + the **L13** spec (§-1 merge baseline, §0 carry-forward, goals, handoff + `.kimi-done` with `LOOP=L13`).

**Scope:** Scheduler cron/one-shot with Matrix delivery; CLI session binding for Matrix-scheduled tasks; tests + policy checks; teardown.

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop log: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- Kimi script: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
