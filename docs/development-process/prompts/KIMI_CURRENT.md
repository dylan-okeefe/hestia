# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L32a merged at `7ea4a53`; L32b queued)

---

## Current task

**Active loop:** **L32b** — `ContextBuilder` named ordered prefix-layer registry. Drop the per-call `*_prefix` kwargs from `build()` (no real call site uses them); replace the four parallel conditional concatenations with a `_PrefixLayer` registry so the assembly order is data, not code.

**Spec:** [`../kimi-loops/L32b-context-prefix-registry.md`](../kimi-loops/L32b-context-prefix-registry.md)

**Branch:** `feature/l32b-context-prefix-registry` from `develop` tip `7ea4a53` (post-L32a merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **4 commits**, ≤ **1 new test module**. Single file under `src/` (`src/hestia/context/builder.py`), one new test file. Do **not** chase ruff cleanups, do **not** touch the tokenize cache (that's L32c), do **not** add new prefix layers.

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L32a-delete-dead-types.md`](../kimi-loops/L32a-delete-dead-types.md) (merged at `7ea4a53`; v0.7.6; tests 704/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L32b
BRANCH=feature/l32b-context-prefix-registry
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
