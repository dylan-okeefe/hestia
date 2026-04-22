# L50 — commands.py split into package

**Status:** Spec only. Feature branch work; do not merge to `develop` until
release-prep merge sequence.

**Branch:** `feature/l50-commands-split` (from `develop`)

## Goal

Split `src/hestia/commands.py` (~1200 lines, 42 KB, 30+ handlers) into a
`src/hestia/commands/` package by domain.

## Scope

1. **Create package structure**
   - `src/hestia/commands/__init__.py` — re-export public CLI entry points.
   - `src/hestia/commands/chat.py` — `_cmd_chat`, `_cmd_chat_history`, etc.
   - `src/hestia/commands/scheduler.py` — `_cmd_schedule_add`, `_cmd_schedule_list`, etc.
   - `src/hestia/commands/policy.py` — `_cmd_policy_show`, `_cmd_policy_set`, etc.
   - `src/hestia/commands/tools.py` — `_cmd_tool_list`, `_cmd_tool_run`, etc.
   - `src/hestia/commands/style.py` — `_cmd_style_show`, `_cmd_style_set`, etc.
   - Additional modules as needed (e.g., `voice.py`, `admin.py`, `config_cmd.py`).

2. **Preserve public API**
   - `src/hestia/app.py` imports should still work.
   - CLI registration (`cli()` function) should remain accessible from the package.

3. **Reduce import graph**
   - Each command module imports only what it uses.
   - No cross-domain imports unless genuinely shared.

4. **Move shared helpers**
   - Any helpers used by multiple domains go in `src/hestia/commands/_shared.py`.

## Tests

- All existing CLI tests must pass without modification (pure refactor).
- `pytest tests/cli/ tests/unit/ -q` green.
- Import smoke test: `python -c "from hestia.commands import cli; print('ok')"`.

## Acceptance

- `src/hestia/commands.py` is deleted (no remnant).
- Each new module is under 300 lines.
- `mypy src/hestia` reports 0 errors.
- `ruff check src/` remains at baseline.
- `.kimi-done` includes `LOOP=L50`.

## Handoff

- Write `docs/handoffs/L50-commands-split-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Advance `KIMI_CURRENT.md` to next queued item.
