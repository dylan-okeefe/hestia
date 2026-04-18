# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L31 merged at `2f20850`; L32-L33 split into 6 mini-loops; L32a queued)

---

## Current task

**Active loop:** **L32a** — delete dead `TurnState` and `ToolResult` from `src/hestia/core/types.py`. The orchestrator has its own `TurnState` in `src/hestia/orchestrator/types.py`; the `core/types.py` definitions are unused booby traps for future contributors.

**Spec:** [`../kimi-loops/L32a-delete-dead-types.md`](../kimi-loops/L32a-delete-dead-types.md)

**Branch:** `feature/l32a-delete-dead-types` from `develop` tip `2f20850` (post-L31 merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **3 commits**, ≤ **1 new test module**. Single theme, single file under `src/`. Do **not** touch the context builder, the orchestrator engine, or anything else outside `src/hestia/core/types.py` and `tests/unit/test_core_types_dead_code_removed.py`.

**Why so small:** This is the first of an 8-loop sequence (L32a, L32b, L32c, L33a, L33b, L33c, L34, L35) replacing what used to be 4 monster loops. Each mini-loop has one job and finishes inside ~40 Kimi steps. The launcher's `--max-steps-per-turn` is now 250, but the spec is sized to fit under 100 anyway.

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L31-engine-cleanup.md`](../kimi-loops/L31-engine-cleanup.md) (merged at `2f20850`; v0.7.5; tests 701/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md) — the L31 entry explains why L32/L33 were split.

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L32a
BRANCH=feature/l32a-delete-dead-types
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked (e.g. §1 grep finds an unexpected import), `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
