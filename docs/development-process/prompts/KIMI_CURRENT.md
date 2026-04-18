# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L25 queued — email adapter read + draft)

---

## Current task

**Active loop:** **L25** — implement email integration (IMAP read/search/list +
SMTP/IMAP draft flow, with send gated by confirmation behavior from L23).

**Spec:** [`../kimi-loops/L25-email-adapter-read-and-draft.md`](../kimi-loops/L25-email-adapter-read-and-draft.md)

**Branch:** `feature/l25-email-adapter` from `develop` tip `c88c60e`.

**Kimi prompt:** Read this file, then execute the full spec at the linked file.
Implement every section in order, including tests/docs/handoff and `.kimi-done`.
Stop and report immediately if any section fails.

**Scope (summary, see spec for detail):**

- Add `EmailAdapter` tool provider and `EmailConfig` wiring.
- Implement `email_list`, `email_read`, `email_search`, `email_draft`,
  `email_send`, `email_move`, `email_flag`.
- Keep send operations confirmation-gated and disabled in subagent/scheduler by
  default trust settings.
- Add integration and sanitization tests.
- Add setup docs and changelog/version updates.

**Do not merge to `develop` in this loop.** Push the feature branch and stop
only after writing `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L24-prompt-injection-detection-and-egress-audit.md`](../kimi-loops/L24-prompt-injection-detection-and-egress-audit.md)
- Brainstorm source: [`../design-artifacts/brainstorm-april-13.md`](../design-artifacts/brainstorm-april-13.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L25
BRANCH=feature/l25-email-adapter
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=<count>
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a
`BLOCKER=<reason>` line.
