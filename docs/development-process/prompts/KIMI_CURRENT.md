# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L33b merged at `f7dcd91`; L33c queued — closes L33 arc)

---

## Current task

**Active loop:** **L33c** — skills experimental flag + minor polish, closing the L33 arc. Three small, independent fixes:

1. Gate the skills framework (`@skill` decorator, `SkillRegistry.register`, `hestia skills *` CLI) behind `HESTIA_EXPERIMENTAL_SKILLS=1` so users get a clear "this is preview, opt in via env var" error instead of silent no-op.
2. Hoist `_format_datetime` from a closure inside the schedule-show command up to module scope.
3. Move `DefaultPolicyEngine.should_delegate`'s inline keyword list into `DEFAULT_DELEGATION_KEYWORDS` constant + new `PolicyConfig.delegation_keywords` config field.
4. Lock the `MatrixAdapter._extract_in_reply_to` schema validation contract with a regression test (no production code change).

**Spec:** [`../kimi-loops/L33c-skills-flag-and-polish.md`](../kimi-loops/L33c-skills-flag-and-polish.md)

**Branch:** `feature/l33c-skills-flag-and-polish` from `develop` tip `f7dcd91` (post-L33b merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **5 commits**, ≤ **2 new test modules** (the spec describes 3 test files but two are tiny — bundle them into one of the test commits if convenient). Final commit bundles version bump + ADR-0022 + L33-arc handoff. Do **not** add any new feature, do **not** rewrite the README skills section beyond the small heading + callout the spec asks for.

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.** L33b shipped with one staged-but-uncommitted bug fix that Cursor caught. Don't repeat that.

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L33b-email-session-reuse.md`](../kimi-loops/L33b-email-session-reuse.md) (merged at `f7dcd91`; v0.7.10; tests 726/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L33c
BRANCH=feature/l33c-skills-flag-and-polish
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
