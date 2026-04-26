# L57 — App Bootstrap Cleanup

## Scope

Reduce `app.py` bloat by collapsing repetition, simplifying the context facade,
and relocating subsystem-specific code.

## Commits

| Commit | Section | Description |
|--------|---------|-------------|
| `25793c6` | §1 | Extract `_get_session_for_tool()` and `_verify_task_ownership()` helpers in scheduler tools |
| `d5e9e07` | §3 | Move `_compile_and_set_memory_epoch` to `persistence/memory_epochs.py` |
| `525e405` | §2 | Replace 21 `CliAppContext` property delegates with `__getattr__` |

## Files changed

- `src/hestia/tools/builtin/scheduler_tools.py` — `_get_session_for_tool` + `_verify_task_ownership` helpers; ~29 lines of duplication removed
- `src/hestia/persistence/memory_epochs.py` — **new** module with `_compile_and_set_memory_epoch`
- `src/hestia/app.py` — removed `_compile_and_set_memory_epoch`, simplified `CliAppContext`
- `src/hestia/commands/meta.py` — updated import to `persistence.memory_epochs`
- `src/hestia/commands/chat.py` — updated import to `persistence.memory_epochs`

## Quality gates

- **Tests:** 89 passed (scheduler + memory + orchestrator + telegram)
- **Ruff:** All checks passed
- **Mypy:** No issues found

## Notes

- `CliAppContext` kept 3 explicit properties (`confirm_callback`, `reflection_scheduler`, `style_scheduler`) because they do non-trivial work (setter, lazy construction).
- `__getattr__` tries `self._core` first, then `self._features` for fallback.

## Merge status

**Do NOT merge to develop.** v0.11 feature-branch work.
Branch: `feature/l57-app-bootstrap-cleanup`
