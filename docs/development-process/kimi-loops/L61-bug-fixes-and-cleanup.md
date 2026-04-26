# L61 — Bug Fixes and Minor Cleanup

**Status:** Outline spec. Branch from `develop`.

**Branch:** `feature/l61-bug-fixes-and-cleanup`

## Goal

Fix four duplicate-definition bugs and three minor code-quality issues.

Full detail in:
`docs/development-process/reviews/docs-and-code-overhaul-april-26.md` Part 2.2 and 2.4.

## Scope

### §1 — Four duplicate-definition bugs

1. **`_compile_and_set_memory_epoch`** — delete copy in `app.py`, import from
   `persistence/memory_epochs.py`
2. **`TransitionCallback`** — move to `orchestrator/types.py`, update imports in
   `assembly.py`, `finalization.py`, `execution.py`
3. **`_sanitize_user_error`** — pick one canonical location (suggest
   `TurnFinalization.sanitize_user_error` and have engine import it), delete other
4. **`ScheduledTask.__post_init__`** — add "neither set" guard:
   `if not (bool(self.cron_expression) or bool(self.fire_at)): raise ValueError(...)`

### §2 — Minor cleanup

1. **`WebSearchError` lazy import** — add directly to `classify_error` type-dispatch
   mapping since it now inherits `HestiaError`
2. **`list_dir.py` async wrapping** — wrap entire `iterdir()` + stat loop in a single
   `asyncio.to_thread` instead of per-item calls
3. **`engine.py` audit** — after §1 fixes, check if additional responsibilities can
   move out to hit ~300-line coordinator target

## Acceptance

- All four duplicate definitions resolved
- `ScheduledTask` rejects both-None and both-set
- Tests updated/added for new validation
- `mypy` and `ruff` clean on changed files

## Dependencies

None.
