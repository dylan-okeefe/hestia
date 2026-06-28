# Handoff: L234–L236 — Tour Commands Arc

## Outcome

Implemented a runtime-introspectable command registry and built `/commands`, `/help`, and `/tour` on top of it across CLI, Telegram, and Matrix.

## Branches

- `feature/l234-tour-commands-registry` — Loop A: registry + migrated meta-commands
- `feature/l235-tour-commands-reference` — Loop B: `/commands` reference and `/help` alias
- `feature/l236-tour-walkthrough` — Loop C: `/tour`, `/continue`, `/endtour` narrated walkthrough

## What changed

### Loop A — Registry (`src/hestia/commands/registry.py`)

- `Command`, `CommandContext`, `CommandRegistry`, `command_from_handler()`, `validate_registry()`.
- Migrated `/quit`, `/exit`, `/reset`, `/compact`, `/history`, `/session`, `/refresh`, `/tokens`, `/help` onto the registry in `src/hestia/commands/meta.py`.
- Exposed registry cross-platform via `get_default_registry()` and re-exports in `src/hestia/commands/__init__.py` and `src/hestia/app.py`.
- ADR: `docs/adr/ADR-050-command-registry.md`.

### Loop B — `/commands` (`src/hestia/commands/meta.py`, platform adapters)

- `render_commands_reference()` lists name, aliases, summary; grouped by category or alphabetical.
- `/help` registered as an alias of `/commands`; hardcoded help list removed.
- Telegram and Matrix adapters route `/commands` and `/help` to the registry handler.

### Loop C — `/tour` (`src/hestia/commands/tour.py`)

- 9 static narrated steps covering chat, commands, sessions, memory, context, tools, workflows/scheduling, platforms/voice, wrap-up.
- `/tour` starts/restarts, `/continue` advances, `/endtour` clears cursor.
- Cursor keyed to `(conversation_id, platform_user_id)` using existing per-conversation state storage.
- Group rooms: `/tour` blocked with DM-only reply; `/continue`/`/endtour` no-op.
- Drift guards ensure every registry command and major capability appears in at least one step.

## Tests

- `tests/unit/commands/test_registry.py`
- `tests/unit/commands/test_commands_reference.py`
- `tests/unit/commands/test_tour.py`
- Updated adapter tests in `tests/unit/test_telegram_adapter.py` and `tests/unit/test_matrix_adapter.py`

Targeted test run: 122 passed.

## Quality gates

- `uv run pytest tests/unit/commands/ tests/unit/test_cli_meta_commands.py tests/unit/test_telegram_adapter.py tests/unit/test_matrix_adapter.py -q` → 122 passed
- `uv run ruff check <changed files>` → clean
- `uv run mypy <changed source files>` → no issues

## Merge status

Feature branches are pushed but **not merged to develop**. Awaiting Dylan's review/approval.
