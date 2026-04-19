# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L36 merged at `ecdbe3d`; v0.8.0 still locally tagged at `c5f68ea`; overnight queue continues at L37)

---

## Current task

**Active loop:** **L37** — Code cleanup sweep: kill dead `hasattr` checks, no-op identity expressions, the over-indented `_cmd_schedule_add` body, hoist three inlined CLI commands into `commands.py`, and crunch the ruff baseline from 43 → ≤ 23. Behavior-preserving across all four commits.

**Spec:** [`../kimi-loops/L37-code-cleanup-sweep.md`](../kimi-loops/L37-code-cleanup-sweep.md)

**Branch:** `feature/l37-code-cleanup-sweep` from `develop` tip `ecdbe3d` (post-L36 merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **4 commits**, **0 new test modules**. One theme per commit (per-commit revertability is the whole point of this loop).

**Updated baselines from L36 merge:** **778 passed, 6 skipped**; mypy **0**; ruff **43** (not 44 — L36 already collapsed one). Spec target was "≤ 24"; with the new starting point, please drive ruff to **≤ 23** to honor the original "fix at least 20" rule. If 20 fixes lands you at 24, that's also acceptable — better a clean partial than an incomplete loop.

**Critical recaps:**

- **One theme per commit.** Mixing themes makes the bisect harder if a regression slips in.
- **No `# noqa` without rationale.** If you add one, surface it in the handoff with one sentence of justification.
- **Stop early on the ruff crunch** if you hit ~150 iterations with checks remaining. Better a partial L37 than a stalled `.kimi-done`.
- **`pyproject.toml` bump:** `0.8.1.dev0` → `0.8.1.dev1`.
- **`KIMI_CURRENT.md` and `kimi-loop-log.md` are out of scope.**

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.**

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (L36→**L37**→L38; L39+L40 deferred)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md) Stage D L37 + Copilot findings 5/7/8/10
- Prior loop: [`../kimi-loops/L36-app-commands-split.md`](../kimi-loops/L36-app-commands-split.md) (merged at `ecdbe3d`; tests 778/0/6; ruff 43)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L37
BRANCH=feature/l37-code-cleanup-sweep
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
