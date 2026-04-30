# L87 — Type Safety & Code Deduplication (April 29 Code Review)

**Status:** In progress  
**Branch:** `feature/l87-april-29-types-dedup` (from `develop`)  
**Scope:** Type annotation fixes and removing duplicate definitions. No runtime behavior change.

---

## Items

| ID | Issue | File | Fix |
|----|-------|------|-----|
| T1 | `ConfirmCallback` defined in two places | `src/hestia/orchestrator/engine.py`, `src/hestia/orchestrator/execution.py` | Define once in `execution.py`, import in `engine.py` |
| T2 | `ReflectionRunner._on_failure` typed as `Any` | `src/hestia/reflection/runner.py` | Change to `Callable[[str, Exception], None] \| None` |
| T3 | Literal `"scheduler"` in session check | `src/hestia/policy/default.py` | Extract `PLATFORM_SCHEDULER` constant or remove dead check |

---

## T1 Detail: Deduplicate `ConfirmCallback`

Both `engine.py` (line 46) and `execution.py` (line 31) define:
```python
ConfirmCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]
```

`engine.py` is the one imported by `app.py`. `execution.py` uses it internally.

Fix:
- Keep the definition in `execution.py` (it's the lower-level module)
- Remove the duplicate from `engine.py`
- In `engine.py`, import `ConfirmCallback` from `execution.py`

Verify `app.py` and any other importers still resolve the type correctly.

## T2 Detail: `ReflectionRunner._on_failure` type

Current annotation is `Any | None`. Change to:
```python
from collections.abc import Callable

_on_failure: Callable[[str, Exception], None] | None
```

Import `Callable` from `collections.abc` if not already imported.

## T3 Detail: `PLATFORM_SCHEDULER` literal

Line 258 of `default.py` has `session.platform == "scheduler"`. No code currently creates sessions with `platform="scheduler"` — the scheduler uses `scheduler_tick_active` ContextVar instead.

Fix: Either extract a constant `PLATFORM_SCHEDULER = "scheduler"` or remove the dead check if it's truly unreachable. If removing, verify no tests depend on it.

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- `pytest` green
- `mypy` 0 errors in changed files
- `ruff` at baseline or better
- `.kimi-done` includes `LOOP=L87`

## Handoff

- Write `docs/handoffs/L87-april-29-types-dedup-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
