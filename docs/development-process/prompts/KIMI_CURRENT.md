# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L35c merged at `71ea99f`; v0.8.0 still untagged; L35d is the final L35 mini-loop)

---

## Current task

**Active loop:** **L35d** — `UPGRADE.md` (root) + `[0.8.0]` CHANGELOG amendment + L35-arc handoff. **Docs-only loop.** No production code changes. **No `pyproject.toml` bump** (v0.8.0 is the target tag; do not create a `[0.8.1]` section).

**Spec:** [`../kimi-loops/L35d-upgrade-doc-and-changelog.md`](../kimi-loops/L35d-upgrade-doc-and-changelog.md)

**Branch:** `feature/l35d-upgrade-doc-and-release-prep` from `develop` tip `71ea99f` (post-L35c merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **3 commits**, **0 new test modules**. Files in scope: `UPGRADE.md` (new at repo root), `CHANGELOG.md` (amend `[0.8.0]` only), `docs/handoffs/L35-pre-release-fixes-arc-handoff.md` (new).

**Per-loop reminders:**

- The `[0.8.0]` block already exists in CHANGELOG (added by `chore(release): v0.8.0` at `d9b889d`). **Amend that block; do not create `[0.8.1]`.** Add three new bullets under "Bug fixes & hardening" (style disable, policy show, join_overhead cache), a new "New diagnostic commands" subsection (hestia doctor), and a new "Upgrade docs" subsection (UPGRADE.md). Update the test-count line at the bottom of the block to `~778 passed`.
- `UPGRADE.md` section ordering is verbatim per spec — every section header listed must appear in the same order.
- Reference `hestia doctor` (now real, post-L35c) in `UPGRADE.md` step 6.
- `docs/handoffs/L35-pre-release-fixes-arc-handoff.md` covers all four mini-loops (L35a + L35b + L35c + L35d) as one document. ≤ 120 lines. Include the loop manifest table (branch, merge commit, lines changed, tests added).

**Do NOT:** create `tests/docs/test_upgrade_md.py` (the L34 README-link test already walks `UPGRADE.md` if at repo root); add `hestia upgrade` references that imply the command exists (L39 deferred); touch any file outside the three named above; bump `pyproject.toml`.

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.**

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (L35a→b→c→**d**→Cursor-tag→L36→L37→L38; L39+L40 deferred)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md) §5 + §6
- Prior loop: [`../kimi-loops/L35c-hestia-doctor.md`](../kimi-loops/L35c-hestia-doctor.md) (merged at `71ea99f`; tests 778/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L35d
BRANCH=feature/l35d-upgrade-doc-and-release-prep
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
