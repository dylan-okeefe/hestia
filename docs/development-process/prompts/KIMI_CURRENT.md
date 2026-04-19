# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L34 merged at `d51d816`; pre-release-plan added at `6317707`; L35 split into L35a/b/c/d; v0.8.0 not yet tagged)

---

## Current task

**Active loop:** **L35a** — pre-release fixes bundle 1: `style disable` Click signature + `ContextBuilder._join_overhead` lazy cache. **Two small fixes**, two new test modules, no `pyproject.toml` bump (v0.8.0 already set on develop and is what L35a-d will tag).

**Spec:** [`../kimi-loops/L35a-style-and-overhead-fixes.md`](../kimi-loops/L35a-style-and-overhead-fixes.md)

**Branch:** `feature/l35a-style-and-overhead-fixes` from `develop` tip `6317707` (post-pre-release-plan doc).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **4 commits**, ≤ **2 new test modules** (`tests/unit/test_cli_style_disable.py`, `tests/unit/test_context_builder_join_overhead_cache.py`). Files in scope: `src/hestia/cli.py`, `src/hestia/context/builder.py`, the two new test files, and `docs/handoffs/L35a-style-and-overhead-fixes-handoff.md`.

**Do NOT:** bump `pyproject.toml`; touch `CHANGELOG.md`; create new shared utility modules; rewrite the `_cmd_policy_show` body (that's L35b); add a `hestia doctor` command (that's L35c); write `UPGRADE.md` (that's L35d).

**Audit while in `cli.py`:** `git grep -n '^def [a-z_]\+(app: CliAppContext)' src/hestia/cli.py`. Any match without `@click.pass_obj` or `@run_async` above it has the same bug — fix in the same commit as the `style_disable` fix and list in the handoff. Likely candidates: any `*_disable` / `*_enable` pattern.

**`_join_overhead` cache edge case:** Do **not** cache the `0` result that arises from "fewer than 2 messages available to measure". Leave `self._join_overhead = None` so the next `build()` with more history can compute the real value. The spec includes the exact pattern.

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.** L33b shipped with one staged-but-uncommitted bug fix that Cursor caught; L33c, L34, L32a/b/c, L33a/c were all clean. Stay clean.

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (L35a→b→c→d→Cursor-tag→L36→L37→L38; L39+L40 deferred)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md)
- Prior loop: [`../kimi-loops/L34-public-release-polish.md`](../kimi-loops/L34-public-release-polish.md) (merged at `d51d816`; v0.7.12; tests 741/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L35a
BRANCH=feature/l35a-style-and-overhead-fixes
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
