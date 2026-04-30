# L87 — Type Safety & Code Deduplication

## Intent & Meaning

Small code-quality sweep: remove a duplicate type alias, tighten an overly-broad `Any` annotation, and replace a magic string with a named constant. No runtime behavior change.

## Changes Made

### T1 — Deduplicate `ConfirmCallback` (`src/hestia/orchestrator/engine.py`, `src/hestia/orchestrator/execution.py`)

- **Kept** the canonical definition in `execution.py` (lower-level module).
- **Removed** the duplicate definition from `engine.py`.
- **Added** explicit re-export in `engine.py`:  
  `from hestia.orchestrator.execution import ConfirmCallback as ConfirmCallback`
- Cleaned up now-unused `Awaitable` import from `engine.py`.
- `app.py` and `platforms/runners.py` continue to import from `engine.py` without changes.

### T2 — Tighten `ReflectionRunner._on_failure` type (`src/hestia/reflection/runner.py`)

- Changed `_on_failure` annotation from `Any | None` to `Callable[[str, Exception], None] | None`.
- Updated `set_failure_handler` parameter type to match.
- Added `from collections.abc import Callable` import.

### T3 — Extract `PLATFORM_SCHEDULER` constant (`src/hestia/policy/constants.py`, `src/hestia/policy/default.py`)

- **Added** `PLATFORM_SCHEDULER: Final[Literal["scheduler"]] = "scheduler"` to `constants.py` alongside the existing `PLATFORM_SUBAGENT` constant.
- **Updated** `default.py` to import and use `PLATFORM_SCHEDULER` instead of the bare string `"scheduler"` in `filter_tools()`.

## Verification

- `pytest tests/unit/ tests/integration/ -q` → **1031 passed, 6 skipped**
- `mypy src/hestia/orchestrator/engine.py src/hestia/orchestrator/execution.py src/hestia/reflection/runner.py src/hestia/policy/default.py src/hestia/policy/constants.py src/hestia/app.py src/hestia/platforms/runners.py` → **no issues**
- `ruff check src/hestia/orchestrator/engine.py src/hestia/orchestrator/execution.py src/hestia/reflection/runner.py src/hestia/policy/default.py src/hestia/policy/constants.py src/hestia/app.py src/hestia/platforms/runners.py` → **all checks passed**

## Commits

```
refactor(orchestrator): deduplicate ConfirmCallback type alias
fix(reflection): tighten _on_failure type annotation
refactor(policy): extract PLATFORM_SCHEDULER constant
```

## Risks & Follow-ups

- None. These are purely static changes; runtime behavior is unchanged.
