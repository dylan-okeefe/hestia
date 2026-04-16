# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-15 (**L17 queued — release v0.2.0**)

---

## Current task

**Active loop:** **L17** — Release v0.2.0 (promote develop → main, tag, branch cleanup)

**Spec:** [`../orchestration/kimi-loops/L17-release-v0.2.0.md`](../orchestration/kimi-loops/L17-release-v0.2.0.md)

**Branch:** This loop operates directly on `develop` and `main`. No new feature branch.

**Kimi prompt:** Read `docs/prompts/KIMI_CURRENT.md`, then execute the full spec at the linked file. Follow every phase (1–7) in order. Stop and report immediately if any phase fails. Write the `.kimi-done` artifact at the end.

**Scope:** Pre-flight verification, tag development-history-snapshot, prep v0.2.0 commits, promote develop → main, tag v0.2.0, push, branch cleanup, gc, final verification.

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Loop log: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- Kimi script: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
