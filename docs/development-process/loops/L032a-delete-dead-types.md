# Kimi loop L32a — delete dead `TurnState` and `ToolResult` from `core/types.py`

## Hard step budget

≤ **3 commits**, ≤ **1 new test module**, no exploration outside the listed files. Stop the moment the version-bump commit lands; write `.kimi-done`; push; exit.

## Review carry-forward

From L31 (merged at `2f20850`):

- Test baseline: **701 passed, 6 skipped**.
- Mypy baseline: **0**.
- Ruff baseline: **44** — must not regress.

From the external code-quality review (2026-04-18):

- `src/hestia/core/types.py` defines a `TurnState` enum (with `TERMINAL_STATES`). `src/hestia/orchestrator/types.py` defines a **different** `TurnState`. The orchestrator imports the orchestrator one. The `core/types` one is never imported anywhere. Booby trap for future contributors.
- `src/hestia/core/types.py` also defines a `ToolResult` dataclass that is never used — the codebase uses `Message(role="tool", ...)` everywhere.

**Branch:** `feature/l32a-delete-dead-types` from `develop` post-L31.

**Target version:** **0.7.6** (patch — internal cleanup, no behavior change).

---

## Scope

### §1 — Verify nothing imports the dead names

```bash
git grep -n "from hestia.core.types import" -- src tests | grep -E "(TurnState|TERMINAL_STATES|ToolResult)"
```

Must be empty. If anything matches, **stop and report blocker** rather than rewriting imports — the dead-code claim does not hold and L32a needs re-scoping.

### §2 — Delete the dead names

In `src/hestia/core/types.py`:

- Remove the `TurnState` enum and the `TERMINAL_STATES` constant.
- Remove the `ToolResult` dataclass.
- If the file becomes empty (only the module docstring remains), leave a `__all__: list[str] = []` line.
- Remove now-unused imports (`Enum`, `dataclass`, etc.) from the top of the file.

### §3 — Anti-regression test

`tests/unit/test_core_types_dead_code_removed.py`:

```python
"""Lock the contract that TurnState and ToolResult live in orchestrator/types.py only."""

import hestia.core.types as core_types


def test_turnstate_not_in_core_types():
    assert not hasattr(core_types, "TurnState")
    assert not hasattr(core_types, "TERMINAL_STATES")


def test_toolresult_not_in_core_types():
    assert not hasattr(core_types, "ToolResult")


def test_orchestrator_turnstate_still_exists():
    from hestia.orchestrator.types import TurnState  # noqa: F401
```

### §4 — Version bump + CHANGELOG (single commit)

- `pyproject.toml` → `0.7.6`.
- `uv lock`.
- One CHANGELOG entry under `[Unreleased]` → promoted to `[0.7.6] — 2026-04-18`.
- No new ADR. No new handoff doc (L32a is too small; the L32-umbrella handoff will land with L32c).

---

## Commits (3 total)

1. `refactor(core): delete dead TurnState and ToolResult from hestia.core.types`
2. `test(core): lock dead-code-removed contract for core/types.py`
3. `chore(release): bump to 0.7.6`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Expected results: **702 passed, 6 skipped** (701 baseline + 1 new test module with ~3 tests; pytest counts each `def test_*` separately, so the new module adds 3 tests but the baseline math may show 704 — accept whatever pytest reports as long as failures are 0). Mypy 0. Ruff ≤ 44.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L32a
BRANCH=feature/l32a-delete-dead-types
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

If blocked (e.g. §1 finds an unexpected import), `HESTIA_KIMI_DONE=0` + `BLOCKER=<reason>`.

---

## Critical Rules Recap

- 3 commits, period. Do **not** make a project-wide ruff sweep, do **not** touch `ContextBuilder`, do **not** touch the orchestrator engine.
- One file under `src/`, one new file under `tests/unit/`, plus `pyproject.toml`/`uv.lock`/`CHANGELOG.md`.
- Push the branch and stop.
