# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-14 (**L10 merged; L11 active**)

---

## Current task

**Active loop:** **L11** — [`../orchestration/kimi-loops/L11-test-tools-memory-mock.md`](../orchestration/kimi-loops/L11-test-tools-memory-mock.md)

**Full chain:** [`KIMI_LOOPS_L10_L14.md`](KIMI_LOOPS_L10_L14.md)

**Branch:** Create **`feature/l11-test-tools-memory-mock`** from **`develop`** (must include L10 merge).

**Kimi prompt:** Point Kimi at **`KIMI_CURRENT.md`** + the **L11** spec (same workflow as prior phases: §-1 merge baseline, §0 carry-forward, implement Goal + Deliverables, handoff + `.kimi-done` with `LOOP=L11`).

**Scope:** Mock-inference integration tests — full built-in + meta tool matrix, memory variants, teardown; denied `write_file` / `terminal` with `confirm_callback=None`.

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop log: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- Kimi script: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
