# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Kimi — 2026-04-19 (L45b complete on feature branch; advancing to L45c)

---

## Current task

**Active loop:** **L45c** — `docs/development-process/kimi-loops/L45c-multi-user-docs-and-hardening.md`
on `feature/l45c-multi-user-docs-and-hardening`.

**L45b completion snapshot:**

- Branch: `feature/l45b-memory-user-scope-migration` (pushed to `origin/feature/l45b-memory-user-scope-migration`)
- Implementation commit: `6ea59ed` (FTS5 migration + user-scoped memory queries/tools/epochs + LIKE fallback)
- `.kimi-done`: `LOOP=L45b`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=23`, `TESTS=820 passed, 6 skipped`
- Merge status: **NOT merged to `develop`** (correct per post-release merge discipline)

**Launch sequence now (L45c):**

1. Create/switch to `feature/l45c-multi-user-docs-and-hardening` from `develop`.
2. Run `./scripts/kimi-run-current.sh`.
3. Wait for valid `.kimi-done` (`HESTIA_KIMI_DONE=1`, `LOOP=L45c`).
4. Review diffs + run gates (`pytest`, `mypy src/hestia`, `ruff check src/`).
5. Fix/tighten prompt and rerun L45c if red.
6. When green: push branch to origin, write loop-log entry, advance this file to next queued loop.

---

## Active release-train scope

Scope declaration is now in:

- `docs/development-process/prompts/v0.8.x-multi-user-safety-release-prep.md`

This satisfies post-release merge discipline for naming the upcoming scope.
Feature branches remain unmerged until explicit merge sequencing.

---

## Queued after L45c

- (Next loop to be planned after L45c review)

---

## Existing blocked work (unchanged)

- **L43 voice calls** remains blocked on Dylan-side prerequisites
  (dedicated phone number, Telegram API app, `py-tgcalls` readiness, Piper assets).

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Multi-user release scope: [`v0.8.x-multi-user-safety-release-prep.md`](v0.8.x-multi-user-safety-release-prep.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
