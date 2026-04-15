# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-15 (**L15 queued — security & bug fixes**)

---

## Current task

**Active loop:** **L15** — Security & bug fixes (pre-public hardening)

**Spec:** [`../orchestration/kimi-loops/L15-security-bug-fixes.md`](../orchestration/kimi-loops/L15-security-bug-fixes.md)

**Branch:** `feature/l15-security-hardening` (create from `develop`)

**Kimi prompt:** Read `docs/prompts/KIMI_CURRENT.md`, then execute the full spec at the linked file. Create the branch, implement every section (§1–§5), run tests + ruff after each commit, write the handoff report and `.kimi-done` artifact.

**Scope:** Fix SSRF (redirect + DNS rebinding), terminal process group kill, NameError guard cleanup, atomic inline index write, allowed_users deny-all default.

---

## Queue (after L15)

| Order | Spec |
|-------|------|
| L16 | [`L16-pre-public-cleanup.md`](../orchestration/kimi-loops/L16-pre-public-cleanup.md) — archive handoffs, skills docs, asyncpg optional, README fixes, lazy imports, model_name validation |

---

## Reference

- Queue: [`../orchestration/kimi-phase-queue.md`](../orchestration/kimi-phase-queue.md)
- Orchestration: [`../HANDOFF_STATE.md`](../HANDOFF_STATE.md)
- Loop log: [`../orchestration/kimi-loop-log.md`](../orchestration/kimi-loop-log.md)
- Kimi script: [`../../scripts/kimi-run-current.sh`](../../scripts/kimi-run-current.sh)
