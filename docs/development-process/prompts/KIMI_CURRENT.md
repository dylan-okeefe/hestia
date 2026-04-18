# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L26 queued — reflection loop + proposal queue)

---

## Current task

**Active loop:** **L26** — implement the reflection loop (pattern mining,
proposal generation, and pending proposal queue surfaced at session start).

**Spec:** [`../kimi-loops/L26-reflection-loop-proposals.md`](../kimi-loops/L26-reflection-loop-proposals.md)

**Branch:** `feature/l26-reflection-loop` from `develop` tip `da68436`.

**Kimi prompt:** Read this file, then execute the full spec at the linked file.
Implement every section in order, run tests, update docs/handoff, and write
`.kimi-done` exactly as specified.

**Scope (summary, see spec for detail):**

- Add `ReflectionRunner` three-pass pipeline.
- Add proposal schema/storage with `pending/accepted/rejected/deferred/expired` lifecycle.
- Add scheduler integration for reflection runs during idle hours.
- Add session-start hook that surfaces pending proposals.
- Add CLI for listing/accepting/rejecting/defering proposals.

**Do not merge to `develop` in this loop.** Push the feature branch and stop
only after writing `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L25-email-adapter-read-and-draft.md`](../kimi-loops/L25-email-adapter-read-and-draft.md)
- Brainstorm source: [`../design-artifacts/brainstorm-april-13.md`](../design-artifacts/brainstorm-april-13.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L26
BRANCH=feature/l26-reflection-loop
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=<count>
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a
`BLOCKER=<reason>` line.
