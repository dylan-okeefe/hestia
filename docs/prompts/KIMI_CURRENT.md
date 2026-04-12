# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review. **Executor:** follow every step below, then the linked **design** specs (not duplicate prompt files).

**Last set by:** Cursor — 2026-04-12 (Phase 7 cleanup; design-dir source of truth)

---

## Current task (do this now)

1. Read **[`docs/design/kimi-hestia-phase-7-cleanup.md`](../design/kimi-hestia-phase-7-cleanup.md)** and implement it **end-to-end** (all sections, tests, commit, push). That file is the **authoritative spec** for this phase.
2. For **Matrix** and **Phase 8+** planning context only (do not implement unless this file explicitly says so later): [`docs/design/matrix-integration.md`](../design/matrix-integration.md), [`docs/design/hestia-phase-8-plus-roadmap.md`](../design/hestia-phase-8-plus-roadmap.md).
3. Complete the **Handoff report** and **`.kimi-done` artifact`** sections at the bottom of the cleanup design doc — those are part of the task.

---

## Next task (after Cursor review)

Cursor will adjust this file or add a follow-up design/prompt if the review finds gaps. Otherwise see [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md) for the merged roadmap order (Matrix after cleanup unless reprioritized).

---

## Reference

- Full queue (Phases 7 → Matrix → 8–13): [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration contract: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop audit trail (detailed): [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- One-shot CLI (optional): [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
