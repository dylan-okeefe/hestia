# Decisions: tour commands, command registry, and `/commands`

## Status

Resolved 2026-06-27. These decisions apply to Loop A, Loop B, and Loop C of the tour/commands arc.

## 1. Registry design

- Commands are registered by **runtime introspection** of the handler function:
  - `name` — canonical command name (e.g. `/compact`).
  - `aliases` — list of alias strings (e.g. `["/c"]`).
  - `summary` — one-line description, taken from the first line of `func.__doc__`.
  - `long_help` — full docstring.
- NO source-comment parsing, JSDoc-style annotations, or AST walks. The registry is plain Python dataclasses/classes populated by a decorator or explicit call.
- The registry must be reachable from **all platform entry points** (CLI REPL, Telegram, Matrix), not only `src/hestia/commands/meta.py`.

## 2. `/help` becomes an alias for `/commands`

- The existing hardcoded `/help` list in `meta.py` is removed.
- `/help` resolves through the registry and renders the same output as `/commands`.

## 3. `/tour` design

- Pure narration. Progression is **never gated on user action**.
- Ephemeral cursor keyed to `(conversation_id, platform_user_id)`.
- `/tour` starts from step 1; a second `/tour` resets to step 1.
- `/continue` advances one step.
- `/endtour` clears the cursor.
- `/continue` and `/endtour` outside an active tour are no-ops with a friendly "no tour running" message.
- Group rooms: `/tour` does not start; replies DM-only. `/continue` and `/endtour` in a group behave as outside a tour.
- Reuse existing per-conversation state storage; no new persistence table.

## 4. `/commands` output

- Renders the registry catalog: name, aliases, summary.
- Grouped readably (by category if categories are provided, otherwise alphabetically).
- Works on CLI, Telegram, and Matrix.
