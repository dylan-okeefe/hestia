# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Kimi — 2026-04-19 (L45a complete on feature branch; advancing to L45b)

---

## Current task

**Active loop:** **L45b** — `docs/development-process/kimi-loops/L45b-memory-user-scope-migration.md`
on `feature/l45b-memory-user-scope-migration`.

**L45a completion snapshot:**

- Branch: `feature/l45a-trust-identity-plumbing` (pushed to `origin/feature/l45a-trust-identity-plumbing`)
- Implementation commit: `281ae90` (runtime identity ContextVars + per-user trust overrides + scheduler identity inheritance)
- Import sort fix: `80d3724`
- `.kimi-done`: `LOOP=L45a`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=23`, `TESTS=805 passed, 6 skipped`
- Merge status: **NOT merged to `develop`** (correct per post-release merge discipline)

**Launch sequence now (L45b):**

1. Create/switch to `feature/l45b-memory-user-scope-migration` from `develop`.
2. Run `./scripts/kimi-run-current.sh`.
3. Wait for valid `.kimi-done` (`HESTIA_KIMI_DONE=1`, `LOOP=L45b`).
4. Review diffs + run gates (`pytest`, `mypy src/hestia`, `ruff check src/`).
5. Fix/tighten prompt and rerun L45b if red.
6. When green: push branch to origin, write loop-log entry, advance this file to L45c.

---

## Active release-train scope

Scope declaration is now in:

- `docs/development-process/prompts/v0.8.x-multi-user-safety-release-prep.md`

This satisfies post-release merge discipline for naming the upcoming scope.
Feature branches remain unmerged until explicit merge sequencing.

---

## Queued after L45b

- **L45c** — `docs/development-process/kimi-loops/L45c-multi-user-docs-and-hardening.md`

---

## Existing blocked work (unchanged)

- **L43 voice calls** remains blocked on Dylan-side prerequisites
  (dedicated phone number, Telegram API app, `py-tgcalls` readiness, Piper assets).

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Multi-user release scope: [`v0.8.x-multi-user-safety-release-prep.md`](v0.8.x-multi-user-safety-release-prep.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
