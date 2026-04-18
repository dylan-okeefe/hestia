# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-17 (L23 queued — Telegram + Matrix confirmation callbacks)

---

## Current task

**Active loop:** **L23** — Wire real tool-confirmation callbacks into
Telegram (inline keyboard) and Matrix (reply pattern), complementing
L20's `TrustConfig.auto_approve_tools`. After L23, operators who
**want** a mobile confirm prompt on `terminal` / `write_file` /
`email_send` calls finally have one that works.

**Spec:** [`../kimi-loops/L23-platform-confirmation-callbacks.md`](../kimi-loops/L23-platform-confirmation-callbacks.md)

**Branch:** `feature/l23-platform-confirmation` (already created from
`develop` tip `75ea2b5`).

**Kimi prompt:** Read this file, then execute the full spec at the
linked file. Implement every section §1 through §5 in order; §0 review
carry-forward from L22 is already populated. Stop and report
immediately if any section fails. Write the `.kimi-done` artifact at
the end (do not commit it).

**Scope (summary, see spec for detail):**

- §1 Telegram inline-keyboard confirmation callback, implemented in
  `src/hestia/platforms/telegram_adapter.py` and wired from
  `cli.py:1146-1148` (the TODO).
- §2 Matrix reply-pattern confirmation in
  `src/hestia/platforms/matrix_adapter.py`, wired from
  `cli.py:1276-1278` TODO.
- §3 Shared infrastructure: `src/hestia/platforms/confirmation.py`
  with `ConfirmationRequest` dataclass and `ConfirmationStore`
  (in-memory v1).
- §4 `TrustConfig.prompt_on_mobile()` preset method.
- §5 Unit + integration tests, README update, **ADR-0016**
  (ADR-0014/0015 were taken by L21).

**Do not merge to `develop` in this loop.** Push the feature branch
and stop after `.kimi-done`.

**Constraints (from L22 review carry-forward):**

- Preserve `mypy src/hestia` at 0 errors. New platform code is not
  strict-typed yet, but don't add `Any` callbacks without reason.
- If you touch ruff-dirty lines in `cli.py`, fix them in a separate
  `style:` commit.
- Confirmation-timeout / denial paths that close the session must go
  through `Orchestrator.close_session`, not
  `SessionStore.archive_session` — otherwise the L21 handoff
  summarizer gets skipped.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- L20 trust profile: [`../kimi-loops/L20-trust-config-and-web-search.md`](../kimi-loops/L20-trust-config-and-web-search.md)
- Capability audit (primary motivation):
  [`../reviews/capability-audit-april-17.md`](../reviews/capability-audit-april-17.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L23
BRANCH=feature/l23-platform-confirmation
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=0
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a
`BLOCKER=<reason>` line.
