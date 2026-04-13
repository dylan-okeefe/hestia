# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review. **Executor:** follow every step below, then the linked specs.

**Last set by:** Cursor — 2026-04-12 (L01 Matrix adapter after Phase 7 merge)

---

## Current task (do this now)

1. Read **[`docs/orchestration/kimi-loops/L01-matrix-adapter.md`](../orchestration/kimi-loops/L01-matrix-adapter.md)** and execute it **end-to-end** (branch, implementation, tests, ADR-021, push, `.kimi-done`).
2. **Product design (authoritative detail):** **[`docs/design/matrix-integration.md`](../design/matrix-integration.md)** — implement fully per that document.
3. Queue context only: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md).

---

## Next task (after Cursor review)

Cursor advances this file to **L02** (`kimi-loops/L02-phase-8a-identity-reasoning.md`) when Matrix is green, or adds a follow-up if review finds gaps.

---

## Reference

- Full queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration contract: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop audit trail: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- CLI: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
