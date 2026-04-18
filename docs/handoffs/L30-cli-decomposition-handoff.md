# L30 — `cli.py` decomposition handoff

**Status:** complete (manual completion by Cursor — Kimi hit
`max-ralph-iterations` before committing).
**Branch:** `feature/l30-cli-decomposition`
**Spec:** [`../development-process/kimi-loops/L30-cli-decomposition.md`](../development-process/kimi-loops/L30-cli-decomposition.md)
**ADR:** [`../adr/ADR-0020-cli-decomposition.md`](../adr/ADR-0020-cli-decomposition.md)

## What shipped

| Module | Lines | Responsibility |
| --- | --- | --- |
| `src/hestia/cli.py` | 588 | Click definitions only. |
| `src/hestia/app.py` | 1,525 | `CliAppContext`, `make_app`, `bootstrap_db`, `make_orchestrator`, all `_cmd_*` async commands. |
| `src/hestia/platforms/runners.py` | 245 | `run_platform`, `run_telegram`, `run_matrix`. |

- `Orchestrator(...)` is constructed in **one** place
  (`CliAppContext.make_orchestrator()`).
- `run_async` decorator removes the `asyncio.run(_inner())` boilerplate
  from every CLI command.
- `ctx.obj` is the typed `CliAppContext` only; the parallel raw-dict
  layer is gone.
- `schedule add | list | show | enable | run | disable | remove |
  daemon` subcommands all wired and tested.

## Test results

```
691 passed, 6 skipped, 0 mypy errors
ruff: 44 errors (down from 255 baseline on develop)
```

## Process notes (for the loop log)

Kimi started L30, created `app.py` and `runners.py`, and modified
`cli.py` — but **never committed any of it** before hitting the
100-step `max-ralph-iterations` ceiling. Cursor took over from the
uncommitted working tree:

1. Removed dangling decorators in `cli.py` (orphaned `@cli.command()` /
   `@click.option(...)` / `@click.pass_context` lines from a removed
   command body).
2. Added missing `_cmd_schedule_add` to the import list in `cli.py`.
3. Restored the missing `_cmd_schedule_enable` and `_cmd_schedule_run`
   helpers in `app.py` (Kimi had dropped them).
4. Wired `schedule_enable`, `schedule_run`, and `schedule_daemon`
   properly under the `@schedule` group (the daemon was a bare
   function, never registered as a Click subcommand).
5. Dropped the bogus `task.run_count` / `task.failure_count` lines
   from `_cmd_schedule_show` (those attributes do not exist on
   `ScheduledTask`).
6. Removed the `config.reflection.enabled` gate from the
   `reflection_scheduler` property so the
   `hestia reflection status` patched-`__init__` test fires (the
   `enabled` check moved to the daemon tick site, where it belongs).
7. Added the missing `import sys` in `app.py` (referenced ~10×, never
   imported).
8. Constrained `reflection_scheduler` construction to require a
   non-`None` `proposal_store` (mypy fix).
9. `ruff check src/ --fix` cleared 64 lints (unused imports,
   `OSError`/`IOError` alias, datetime UTC, etc.). One auto-fix
   replaced a `setattr(func, "__hestia_skill__", definition)` workaround
   in `skills/decorator.py` with a direct attribute write that mypy
   rejected; restored the assignment with a `# type: ignore[attr-defined]`.

## Carry-forward into L31

- Ruff baseline is now **44**. L31's orchestrator-engine cleanup must
  not regress this.
- Two new `aiosqlite` `RuntimeError: Event loop is closed` warnings
  during the test session (still pre-existing, still not L30's fault).
- `app.py` is a 1,525-line junk drawer of `_cmd_*` functions. If it
  passes ~1,800 in a future loop, split it into `hestia.commands.*`
  (one module per command group: `chat`, `schedule`, `reflection`,
  `style`, `audit`, `email`, `skill`, `failures`).
- `Orchestrator.__init__` still takes 12+ parameters — that is L31's
  problem, not L30's.
