# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-15 (**L18 queued — post-public cleanup + v0.2.1 release**)

---

## Current task

**Active loop:** **L18** — Post-public cleanup + v0.2.1 release

**Spec:** [`../orchestration/kimi-loops/L18-post-public-cleanup-v0.2.1.md`](../orchestration/kimi-loops/L18-post-public-cleanup-v0.2.1.md)

**Branch:** `feature/l18-post-public-cleanup` (create from `develop`).

**Kimi prompt:** Read `docs/prompts/KIMI_CURRENT.md`, then execute the full spec at the linked file. Implement every section §1–§7 in order. Stop and report immediately if any section fails. Write the `.kimi-done` artifact at the end (do not commit it).

**Scope:**
- §1 Fix `SecurityAuditor` `memory_write` → `save_memory` tool-name bug (+ test)
- §2 Atomic per-artifact metadata write
- §3 Move internal AI-orchestration docs to `docs/development-process/` with explanatory README; update all cross-references
- §4 Make CI mypy honest (baseline 44 errors, fail on new ones)
- §5 CHANGELOG + version bump for v0.2.1
- §6 Promote `develop` → `main`, tag v0.2.1, push
- §7 Branch cleanup + final test verification on both branches

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Loop log: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- Kimi script: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
