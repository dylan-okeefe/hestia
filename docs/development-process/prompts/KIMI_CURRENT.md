# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L28 queued — critical bug fixes + dependency hygiene)

---

## Current task

**Active loop:** **L28** — fix the seven correctness/security bugs identified by external reviewers (bleach missing, read_artifact unregistered, email Message-ID, IMAP injection, malformed SINCE fallthrough, dead StyleProfileBuilder stub, draft-unknown UID sentinel) with regression tests for each.

**Spec:** [`../kimi-loops/L28-critical-bugs-and-deps.md`](../kimi-loops/L28-critical-bugs-and-deps.md)

**Branch:** `feature/l28-critical-bugs` from `develop` tip `e2d64a0`.

**Kimi prompt:** Read this file, then execute the full spec at the linked file. Implement each section in order, run required tests, update docs/handoff, and write `.kimi-done` exactly as specified.

**Scope (summary, see spec for detail):**

- Replace archived `bleach` with maintained `nh3` and add to `pyproject.toml`/`uv.lock`.
- Register `read_artifact` in CLI and add `delete_memory` tool.
- Fix `EmailAdapter.create_draft` to assign a real `Message-ID`; remove `draft-unknown` sentinel; raise on UID-lookup miss.
- Escape IMAP quotes in `_parse_search_query`; raise on malformed `SINCE:` instead of silent subject-search fallthrough.
- Delete dead `StyleProfileBuilder.get_profile_dict` stub.
- Bump version to **0.7.2**; CHANGELOG; lockfile in same commit.

**Do not merge to `develop` in this loop.** Push the feature branch and stop only after writing `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L27-personality-that-learns-style-profile.md`](../kimi-loops/L27-personality-that-learns-style-profile.md)
- External reviews driving L28–L35: see the L28 spec's `## Review carry-forward` section.

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L28
BRANCH=feature/l28-critical-bugs
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=<count>
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a `BLOCKER=<reason>` line.
