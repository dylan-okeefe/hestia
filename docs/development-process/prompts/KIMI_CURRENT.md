# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-19 (L35b merged at `852d546`; v0.8.0 still untagged; L35c next — biggest L35 mini-loop)

---

## Current task

**Active loop:** **L35c** — `hestia doctor` command. New `src/hestia/doctor.py` module with nine read-only health checks, `_cmd_doctor` in `app.py`, command registration in `cli.py`, and two new test modules. **No `pyproject.toml` bump.** This is the largest of the four L35 mini-loops; stay disciplined and do not extend scope to auto-fix logic, `hestia upgrade`, or schema migrations (those are L39, deferred).

**Spec:** [`../kimi-loops/L35c-hestia-doctor.md`](../kimi-loops/L35c-hestia-doctor.md)

**Branch:** `feature/l35c-hestia-doctor` from `develop` tip `852d546` (post-L35b merge).

**Kimi prompt:** Read this file, then execute the entire spec at the linked file. Implement each section in order, run required tests, and write `.kimi-done` exactly as specified.

**Hard step budget:** ≤ **5 commits**, ≤ **2 new test modules** (`tests/unit/test_doctor_checks.py`, `tests/cli/test_doctor_command.py`). Files in scope: `src/hestia/doctor.py` (new), `src/hestia/app.py` (single function added), `src/hestia/cli.py` (one new command + one import), the two new test modules, and `docs/handoffs/L35c-hestia-doctor-handoff.md`.

**Step-ceiling discipline reminder:** L29-L31 hit the per-iteration ceiling on loops of this shape. Nine checks × 2 tests is exactly the kind of accumulation that exhausts the step budget. If you find yourself at iteration ~150 with checks still missing, **stop**, commit what you have, write `.kimi-done` as `HESTIA_KIMI_DONE=0` with `BLOCKER=step-ceiling`, and let Cursor finish the rest. Do **not** push a partially-tested module pretending it's done.

**Critical rules from the spec:**

- **Read-only.** No check writes anywhere. `_check_dependencies_in_sync` reads via `uv pip check`; do not run `uv sync` from doctor.
- **Each check returns `CheckResult`.** Never raises. If a check has an uncaught bug, that's a test gap to close.
- **No new dependencies.** Use `httpx` (already in deps), `sqlite3` (stdlib), `subprocess` (stdlib).
- **Disabled platforms are not failures.** Only check what's enabled in `app.config`.
- **No auto-fix logic.** That's L39 (deferred).

**FINAL CHECK BEFORE WRITING `.kimi-done`:** run `git status --porcelain`. **If anything is unstaged/uncommitted, commit it first.**

**Push the branch and stop after writing `.kimi-done`. Do not merge to `develop`.**

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md) (L35a→b→**c**→d→Cursor-tag→L36→L37→L38; L39+L40 deferred)
- Pre-release plan: [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md) §4
- Prior loop: [`../kimi-loops/L35b-policy-show-wiring.md`](../kimi-loops/L35b-policy-show-wiring.md) (merged at `852d546`; tests 753/0/6)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)

---

## `.kimi-done` contract (mandatory, see `.cursorrules`)

```
HESTIA_KIMI_DONE=1
LOOP=L35c
BRANCH=feature/l35c-hestia-doctor
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked, `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.
