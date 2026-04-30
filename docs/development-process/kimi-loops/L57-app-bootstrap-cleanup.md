# L57 — App Bootstrap Cleanup

**Status:** Outline spec. Feature branch work; do **not** merge to `develop`
until v0.11 release-prep.

**Branch:** `feature/l57-app-bootstrap-cleanup` (from `develop`)

## Goal

Reduce `app.py` (713 lines) to pure bootstrap wiring. Move CLI-specific and
repetitive code out.

## Scope

### §1 — Meta-command handler

Already moved in L55 to `commands/meta.py`. Finalize the import wiring.

### §2 — Scheduler tool factory collapse

The five scheduler tool factories repeat the same pattern:
"get platform/user from context → get session → check task ownership → call store".

Extract a `_get_session_for_tool()` helper in `tools/builtin/scheduler_tools.py`
to remove ~50 lines of duplication.

### §3 — CliAppContext facade simplification

`CliAppContext` has ~30 property delegates that forward to `FeatureAppContext`.
Evaluate whether the three-context split (`CoreAppContext`, `FeatureAppContext`,
`CliAppContext`) is still pulling its weight. If `CliAppContext` is just a thin
wrapper, consider flattening to two levels or using `__getattr__` delegation.

### §4 — _compile_and_set_memory_epoch relocation

This method lives in `app.py` but is a memory subsystem concern. Move to
`persistence/memory_epochs.py` or similar.

## Acceptance

- `app.py` under 400 lines.
- No behavioral changes.
- All tests pass.

## Dependencies

- L55 (meta-command move) is prerequisite.
