# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-17 (L22 queued — mypy cleanup + CI strictness ratchet)

---

## Current task

**Active loop:** **L22** — Drive `uv run mypy src/hestia` from 44 errors
to 0, retire the `mypy-baseline.txt` count-based comparison, and flip
`strict = true` on `hestia.policy.*` and `hestia.core.*` as the first
ratchet. At least 20 of the current errors mask real latent bugs
(unchecked `Optional` access, DB row → dataclass coercion), so this is a
bug-fix loop, not just a type-annotation loop.

**Spec:** [`../kimi-loops/L22-mypy-cleanup-and-ci-strictness.md`](../kimi-loops/L22-mypy-cleanup-and-ci-strictness.md)

**Branch:** `feature/l22-mypy-cleanup` (already created from `develop`
tip `d6b7cd3`).

**Kimi prompt:** Read this file, then execute the full spec at the
linked file. Implement every section §-1 through §8 in order; the
§0 review carry-forward from L21 is already populated. Stop and report
immediately if any section fails. Write the `.kimi-done` artifact at the
end (do not commit it).

**Scope (summary, see spec for detail):**

- §1 Missing stubs (`types-croniter`).
- §2 Forward references in `hestia.persistence.sessions` (use
  `TYPE_CHECKING` + `from __future__ import annotations`).
- §3 `Optional` attribute access — **real bugs**, guard or raise.
- §4 Factory-returns-`Any` in `hestia.tools.registry`.
- §5 DB row → dataclass explicit coercions.
- §6 Missing annotations on legacy helpers.
- §7 Orchestrator tool-argument narrowing.
- §8 Remove `mypy-baseline.txt`, add `strict = true` sections for
  `hestia.policy.*` and `hestia.core.*`, update CI to fail on any mypy
  error.

Companion inventory:
[`../reviews/mypy-errors-april-17.md`](../reviews/mypy-errors-april-17.md).

**Do not merge to `develop` in this loop.** Push the feature branch and
stop after `.kimi-done`.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- L21 handoff (just merged):
  [`../../handoffs/L21-context-resilience-handoff.md`](../../handoffs/L21-context-resilience-handoff.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

At successful completion, write `./.kimi-done` with at minimum:

```
HESTIA_KIMI_DONE=1
LOOP=L22
BRANCH=feature/l22-mypy-cleanup
COMMIT=<final commit sha>
TESTS=<pytest summary, e.g. "passed=N failed=0 skipped=M">
MYPY_FINAL_ERRORS=0
```

If blocked, still write `.kimi-done` with `HESTIA_KIMI_DONE=0` and a
`BLOCKER=<reason>` line.
