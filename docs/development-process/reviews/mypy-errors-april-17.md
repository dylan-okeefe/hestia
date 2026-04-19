# Mypy error inventory — April 17, 2026

**Command:** `uv run mypy src/hestia`
**Result:** `Found 44 errors in 12 files (checked 67 source files)`

The CI baseline (`docs/development-process/mypy-baseline.txt`) records the same
count, so CI stays green because the counts match — but no actual typing work
is being enforced. L22 removes the baseline dependency by fixing the real
causes and setting `strict = True` where feasible.

---

## Categories

### A. Missing third-party stubs (3 errors — trivial)

| File | Line | Module |
|------|------|--------|
| `platforms/matrix_adapter.py` | 9 | `nio` |
| `persistence/db.py` | 15 | `asyncpg` |
| `persistence/scheduler.py` | 8 | `croniter` |

**Fix:**

- Install `types-croniter` as a dev dependency.
- Add `[[tool.mypy.overrides]] module = ["nio", "asyncpg"]` with
  `ignore_missing_imports = true` in `pyproject.toml`. (Upstream `matrix-nio`
  and `asyncpg` do not publish `py.typed` markers.)

### B. Forward references to `Turn` / `TurnTransition` in `sessions.py` (6 errors)

```text
src/hestia/persistence/sessions.py:362: Name "Turn" is not defined
src/hestia/persistence/sessions.py:379: Name "Turn" is not defined
src/hestia/persistence/sessions.py:398: Name "TurnTransition" is not defined
src/hestia/persistence/sessions.py:422: Name "Turn" is not defined
src/hestia/persistence/sessions.py:448: Name "Turn" is not defined
src/hestia/persistence/sessions.py:480: Name "Turn" is not defined
```

`Turn` and `TurnTransition` live in `hestia.orchestrator.types`. The file uses
`"Turn"` and `"TurnTransition"` as string annotations but never imports them
under `TYPE_CHECKING`. Mypy can't resolve the forward ref.

**Fix:** Add:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hestia.orchestrator.types import Turn, TurnTransition
```

Then drop the quoted annotations (no longer needed with
`from __future__ import annotations`).

### C. Unchecked `Optional` attribute access (16 errors)

This is the biggest bucket and the one most likely to mask real bugs.

**`SchedulerStore | None` in `cli.py` (9 errors, lines 614, 780, 810, 864, 900,
913, 942, 961, 982):** The scheduler store is constructed lazily; several
command handlers access its methods without re-checking.

Pattern:
```python
store: SchedulerStore | None = _maybe_build_scheduler_store(cfg)
# ...
store.list_tasks_for_session(...)  # mypy: store could be None
```

**Fix:** Either (a) split the scheduler-aware commands into a helper that
takes a non-optional `SchedulerStore` and raises a clear error at the top when
it's None, or (b) move the None check to the command entry points with an
early `raise click.UsageError("scheduler store is not configured")`.

**`SkillState | None` in `cli.py` (4 errors, lines 1547, 1548, 1585, 1586):**
`SkillRegistry.get_state()` returns `SkillState | None` but the code calls
`.value` on it and passes it to `SkillStore.update_state` which requires a
non-None state. Real latent bug if the skill was deregistered mid-run.

**Fix:** Guard with `if state is None: raise ...` before use.

**`Updater | None` in `telegram_adapter.py` (2 errors, lines 54, 64):** The
`Updater` attribute is initialized lazily in `start()`. `stop()` can be called
before `start()` and will NPE.

**Fix:** Either initialize eagerly (preferred — Telegram `Application` is cheap
to instantiate), or add a guard that logs-and-returns in `stop()` when
`self._updater is None`.

**`Session` None in `cli.py:1715`:** `turn_token_budget(None)` is a real bug in
the `hestia check` / diagnostic path — the command tries to show budget stats
but the session wasn't loaded. Either load a session (or fabricate a synthetic
one) or change the diagnostic to skip budget if no session.

### D. `Returning Any` from typed factory callables (7 errors)

| File | Lines |
|------|-------|
| `skills/types.py` | 63 |
| `platforms/matrix_adapter.py` | 111 |
| `persistence/scheduler.py` | 68 |
| `tools/builtin/delegate_task.py` | 219 |
| `tools/builtin/memory_tools.py` | 51, 82, 119 |

All are cases where a function declared to return a concrete type returns
`Any` from an untyped inner closure or `functools.partial`.

**Fix:** Use `typing.cast` at the return site, or tighten the inner closure's
signature so mypy can infer. Example (`memory_tools.py`):

```python
def _make_save_memory(store: MemoryStore) -> Callable[..., Awaitable[str]]:
    async def _save_memory(content: str, tags: list[str] | None = None) -> str:
        ...
    return _save_memory  # no longer Any
```

### E. `scheduler.py` row-to-dataclass coercion (4 errors, lines 68, 265, 281, 362)

SQLite rows come back with loose typing (`datetime | str | None`, etc.) and are
passed directly to `ScheduledTask(...)`. Real latent bug: a NULL `enabled`
column would silently flow through as `None` and pass a truthiness check but
fail the `bool` contract.

**Fix:** Tighten `_row_to_task` with explicit coercions:

```python
enabled = bool(row.enabled) if row.enabled is not None else False
created_at = row.created_at if row.created_at is not None else utcnow()
```

### F. Missing function annotations (7 errors)

`cli.py:1113, 1243`, `telegram_adapter.py:134, 147`, `memory/store.py:187`,
`delegate_task.py:161`, `audit/checks.py:256` (the last is a `set[str]` vs
`list[str]` assignment, not pure missing annotation).

**Fix:** Add `-> None` / proper return and parameter annotations. The
`audit/checks.py` one is a real bug — the variable is declared `list[str]`
but then assigned a `set[str]` literal; pick one and commit to it.

### G. Orchestrator tool-argument type narrowing (2 errors, `engine.py:652, 661`)

`ToolCall.arguments` is `dict[str, Any]` on the type but by the time the
orchestrator extracts it through the response parser chain, mypy sees
`Any | dict[Any, Any] | None`. The registry requires `dict[str, Any]`.

**Fix:** Narrow at the extraction point:

```python
arguments: dict[str, Any] = tc.arguments if isinstance(tc.arguments, dict) else {}
```

And reject malformed tool calls earlier in the pipeline.

---

## Summary count by category

| Category | Error count | Severity |
|----------|-------------|----------|
| A. Missing stubs | 3 | trivial |
| B. Forward refs | 6 | trivial |
| C. Optional access | 16 | **real bugs** |
| D. Factory returns | 7 | cosmetic |
| E. DB coercion | 4 | **real bug risk** |
| F. Missing annotations | 7 | cosmetic |
| G. Orchestrator narrowing | 2 | cosmetic |
| **Total** | **44** | |

At least ~20 of the 44 are flagging real latent bugs (C + E + one F + one G),
not just style noise. That's why L22 is worth doing *now*, not "when
convenient."

---

## L22 plan (summary)

1. Fix A–G in that order; each category is a separate commit.
2. Remove `docs/development-process/mypy-baseline.txt` once count is 0.
3. Flip `.github/workflows/ci.yml`'s type-check step from baseline-diff to
   `uv run mypy src/hestia` (fail on any new error).
4. Optionally add `strict = true` under `[[tool.mypy.overrides]]` for
   `hestia.policy.*` and `hestia.core.*` as a ratchet; expand later.
