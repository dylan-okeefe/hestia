# Kimi loop L37 — code cleanup sweep (engine + cli consistency + ruff baseline crunch)

## Hard step budget

≤ **4 commits**, ≤ **0 new test modules** (cleanup is behavior-preserving), scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L36 (assume green-merged ahead of this loop):

- Test baseline: **~775 passed, 6 skipped**.
- Mypy 0. Ruff 44 (baseline still standing).
- `_cmd_*` functions are now in `src/hestia/commands.py`. Path references in this loop's spec assume that move; if you find a `_cmd_*` still in `app.py`, that's an L36 escape — fix it as commit 0 with a single-line note in the handoff.

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md` Stage D L37 and Copilot review findings 5/7/8/10.

**Branch:** `feature/l37-code-cleanup-sweep` from `develop` post-L36.

**Target version:** **0.8.1.dev1**.

---

## Scope (one commit per theme; do not interleave)

### Commit 1 — Engine + context cleanup

In `src/hestia/orchestrator/engine.py`:

- `_build_failure_bundle` (extracted in L31) currently does `hasattr(session, ...)` checks on a typed dataclass. The dataclass has the field unconditionally — `hasattr` is dead code. Replace with direct attribute access. (Copilot #7)
- Audit the `slot_snapshot` block inside `_build_failure_bundle` — same pattern.

In `src/hestia/platforms/runners.py` `run_platform`:

- The line `app = app if isinstance(app, CliAppContext) else app` (Copilot #5) is a no-op identity operation. Replace with `assert isinstance(app, CliAppContext), "expected CliAppContext"` if mypy needs the narrow, or **delete** if mypy is satisfied without it. Run `mypy` after each option to decide.

In `src/hestia/commands.py` `_cmd_schedule_add` (moved from `app.py` in L36):

- Body is over-indented by one level (Copilot #10). Remove the spurious indent. Verify by running ruff's `E117` check or manual diff against neighboring `_cmd_schedule_*` functions.

Commit message: `refactor(engine+platforms+commands): remove dead checks, no-op identity, over-indent`

### Commit 2 — CLI consistency pass

In `src/hestia/cli.py`:

- `schedule_disable`, `schedule_remove`, `init` currently inline their logic instead of delegating to a `_cmd_*` function in `commands.py` (Copilot #8). Extract each:
  - `_cmd_schedule_disable(app: CliAppContext, name: str)` in `commands.py`
  - `_cmd_schedule_remove(app: CliAppContext, name: str)` in `commands.py`
  - `_cmd_init(app: CliAppContext, ...)` in `commands.py` (preserve all existing options as parameters)
- `cli.py`'s wrappers become standard `@run_async`-decorated thin call-throughs matching the rest of the file.

Verify the test suite still passes without modification. If a test asserts on the inlined logic, the test was reaching too deep — update the test to invoke via `CliRunner` instead.

Commit message: `refactor(cli): hoist schedule_disable, schedule_remove, init into commands.py`

### Commit 3 — Ruff baseline crunch

Run `uv run ruff check src/ tests/ --output-format json | python -c '...'` (or `ruff check --statistics`) to get a per-file count of the 44 baseline errors.

Prioritize, in order:

1. Errors in `app.py` and `platforms/runners.py` — freshly-moved code most likely to hide bugs.
2. `commands.py` — newly-extracted, easiest to fix while the changes are fresh.
3. `cli.py`, `engine.py` — high-traffic files.
4. Everything else.

Stop when you've fixed at least **20 errors** (so the new baseline is **≤ 24**). Do not chase every single one — diminishing returns and step ceiling.

For each fixed rule, prefer `ruff check --fix` first; manual fix only when `--fix` doesn't apply. Do **not** add `# noqa` comments unless the rule is genuinely wrong for the codebase (in which case, add a one-line rationale comment and surface in the handoff).

Commit message: `style(ruff): crunch baseline from 44 to <new count>`

### Commit 4 — Bump + handoff

- `pyproject.toml` → `0.8.1.dev1`
- `uv lock`
- `docs/handoffs/L37-code-cleanup-sweep-handoff.md` — list every file touched, ruff before/after count, any `# noqa` justifications.

Commit message: `chore(release): 0.8.1.dev1; L37 cleanup-sweep handoff`

---

## Required commands

```bash
uv run pytest tests/unit/ tests/integration/ tests/cli/ tests/docs/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

Mypy 0. Ruff ≤ 24. Pytest unchanged from L36.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L37
BRANCH=feature/l37-code-cleanup-sweep
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- **One theme per commit.** If commit N introduces a regression, the bisect is one revert.
- **No new tests** (this is cleanup; existing coverage is what catches regressions).
- **No `# noqa` without rationale.**
- **Stop at 20 ruff fixes** if you're approaching the step ceiling. Better a clean partial than an incomplete loop.
- Push and stop after `.kimi-done`.
