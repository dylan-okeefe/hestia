# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-15 (**L16 queued — pre-public cleanup**)

---

## Current task

**Active loop:** **L16** — Pre-public cleanup (docs, polish, scaffolding removal)

**Spec:** [`../orchestration/kimi-loops/L16-pre-public-cleanup.md`](../orchestration/kimi-loops/L16-pre-public-cleanup.md)

**Branch:** `feature/l16-pre-public-cleanup` (create from `develop`)

**Kimi prompt:** Read `docs/prompts/KIMI_CURRENT.md`, then execute the full spec at the linked file. Create the branch, implement every section (§1–§7), run tests + ruff after each commit, write the handoff report and `.kimi-done` artifact.

**Scope:** Archive handoff state files, document skills system, make asyncpg optional, update README security/quickstart, move lazy imports to module level, require explicit model_name.

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop log: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- Kimi script: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
