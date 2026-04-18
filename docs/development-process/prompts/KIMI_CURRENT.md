# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L27 queued — personality/style profile)

---

## Current task

**Active loop:** **L27** — build the interaction-style profile system so Hestia
adapts communication style automatically while keeping identity (`SOUL.md`)
separate and unchanged.

**Spec:** [`../kimi-loops/L27-personality-that-learns-style-profile.md`](../kimi-loops/L27-personality-that-learns-style-profile.md)

**Branch:** `feature/l27-style-profile` from `develop` tip `980d14f`.

**Kimi prompt:** Read this file, then execute the full spec at the linked file.
Implement each section in order, run required tests, update docs/handoff, and
write `.kimi-done` exactly as specified.

**Scope (summary, see spec for detail):**

- Add style metrics store and nightly builder.
- Add context addendum injection (`[STYLE PROFILE] ...`) with token cap.
- Add CLI reset/inspect controls for style profile.
- Add scheduler integration and tests/docs.
- Keep behavior transparent and resettable.

**Do not merge to `develop` in this loop.** Push the feature branch and stop
only after writing `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L26-reflection-loop-proposals.md`](../kimi-loops/L26-reflection-loop-proposals.md)
- Brainstorm source: [`../design-artifacts/brainstorm-april-13.md`](../design-artifacts/brainstorm-april-13.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L27
BRANCH=feature/l27-style-profile
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=<count>
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a
`BLOCKER=<reason>` line.
