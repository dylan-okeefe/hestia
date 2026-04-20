# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Kimi — 2026-04-19 (L45c complete on feature branch; queue drained)

---

## Current task

**Active loop:** **IDLE** — L45a, L45b, and L45c feature branches are complete and pushed.
Awaiting Cursor review and v0.8.x release-prep merge sequencing.

**L45c completion snapshot:**

- Branch: `feature/l45c-multi-user-docs-and-hardening` (pushed to `origin/feature/l45c-multi-user-docs-and-hardening`)
- Implementation commit: `de231f2` (allow-list wildcard matching + multi-user docs + adapter validation)
- `.kimi-done`: `LOOP=L45c`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=23`, `TESTS=818 passed, 6 skipped`
- Merge status: **NOT merged to `develop`** (correct per post-release merge discipline)

---

## Active release-train scope

Scope declaration is now in:

- `docs/development-process/prompts/v0.8.x-multi-user-safety-release-prep.md`

This satisfies post-release merge discipline for naming the upcoming scope.
Feature branches remain unmerged until explicit merge sequencing.

---

## Completed in this train

- **L45a** — `feature/l45a-trust-identity-plumbing` — Runtime identity ContextVars + per-user trust overrides
- **L45b** — `feature/l45b-memory-user-scope-migration` — Memory user scoping + FTS5 migration + LIKE fallback
- **L45c** — `feature/l45c-multi-user-docs-and-hardening` — Allow-list hardening + multi-user docs

---

## Existing blocked work (unchanged)

- **L43 voice calls** remains blocked on Dylan-side prerequisites
  (dedicated phone number, Telegram API app, `py-tgcalls` readiness, Piper assets).

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Multi-user release scope: [`v0.8.x-multi-user-safety-release-prep.md`](v0.8.x-multi-user-safety-release-prep.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
