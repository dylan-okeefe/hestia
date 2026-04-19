# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L33c merged at `8b5228c`; L33 arc closed; L34 queued)

---

## Current task

**Active loop:** **L34** — public-release polish (README + deployment + email-setup guide + CHANGELOG curation). **Docs-only loop.** No production code changes; minor doc-driving config edits only if absolutely necessary. Bump to v0.7.12.

**Spec:** [`../kimi-loops/L34-public-release-polish.md`](../kimi-loops/L34-public-release-polish.md)

**Branch:** `feature/l34-public-release-polish` from `develop` tip `8b5228c` (post-L33c merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **7 commits** (one per section in §1–§5, plus §6 lint pass and §7 version+handoff bundled together if convenient). ≤ **1 new test module** (the optional README-links walker). Files in scope: `README.md`, `docs/guides/email-setup.md`, `CHANGELOG.md`, `pyproject.toml`/`uv.lock`, `docs/handoffs/L34-public-release-polish-handoff.md`, optionally `tests/docs/test_readme_links.py`.

**Do NOT:** generate any image / asciicast asset (placeholders only); chase production-code cleanups; touch deploy/ unit files (they exist, just document them).

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.** L33b shipped with one staged-but-uncommitted bug fix that Cursor caught; L33c was clean. Stay clean.

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L33c-skills-flag-and-polish.md`](../kimi-loops/L33c-skills-flag-and-polish.md) (merged at `8b5228c`; v0.7.11; tests 741/0/6; closed L33 arc)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L34
BRANCH=feature/l34-public-release-polish
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
