# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-18 (L24 queued — injection detection + egress audit)

---

## Current task

**Active loop:** **L24** — Add prompt-injection detection on tool results and
network egress auditing before email integration lands.

**Spec:** [`../kimi-loops/L24-prompt-injection-detection-and-egress-audit.md`](../kimi-loops/L24-prompt-injection-detection-and-egress-audit.md)

**Branch:** `feature/l24-injection-detection` from `develop` tip `f56e9ad`.

**Kimi prompt:** Read this file, then execute the full spec at the linked file.
Implement every section in order. Stop and report immediately if any section
fails. Write the `.kimi-done` artifact at the end (do not commit it).

**Scope (summary, see spec for detail):**

- Add `src/hestia/security/injection.py` scanner with regex + entropy heuristic.
- Invoke scanner on tool results before they are returned to orchestrator.
- Record egress events for `http_get` and `web_search` via trace store.
- Add `hestia audit egress --since=7d` domain-level reporting.
- Add `SecurityConfig` and wire through `HestiaConfig`.
- Add tests/docs + ADR.

**Do not merge to `develop` in this loop.** Push the feature branch and stop
after `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Prior loop: [`../kimi-loops/L23-platform-confirmation-callbacks.md`](../kimi-loops/L23-platform-confirmation-callbacks.md)
- Capability audit: [`../reviews/capability-audit-april-17.md`](../reviews/capability-audit-april-17.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L24
BRANCH=feature/l24-injection-detection
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=<count>
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a
`BLOCKER=<reason>` line.
