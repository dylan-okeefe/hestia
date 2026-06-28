# Spec: tour commands, `/commands`, and command registry

## Loop A — Docstring-driven command registry (foundation)

### Goal

Introduce a lightweight, runtime-introspectable command registry and migrate existing meta-commands onto it without changing behavior.

### Registry entries

Each entry captures:

- `name`: canonical command string, e.g. `/compact`.
- `aliases`: list of alias strings, e.g. `["/c"]`.
- `summary`: first non-blank line of the handler docstring.
- `long_help`: full handler docstring.
- `category`: optional grouping string.
- `handler`: async callable that implements the command.

Registration can be a decorator or an explicit `registry.register(...)` call.

### Commands to migrate

Migrate these existing meta-commands onto the registry, preserving exact behavior:

- `/quit`, `/exit`
- `/reset`
- `/compact`
- `/history`
- `/session`
- `/refresh`
- `/tokens`
- `/help`

If present, also migrate:

- `/add-topic`, `/remove-topic`, `/topic`, `/remember-global`

### Reachability

The registry must be importable from:

- `src/hestia/commands/meta.py` (CLI REPL)
- `src/hestia/platforms/telegram_adapter.py`
- `src/hestia/platforms/matrix_adapter.py`
- `src/hestia/platforms/cli_adapter.py`

### Tests

- Every migrated command resolves through the registry and behaves identically.
- Registry exposes name/aliases/summary/long-help per command.
- Missing summary or docstring fails a registry lint/drift test.
- Unknown commands still fall through unchanged.

### Commit message

`feat(commands): add docstring-driven command registry and migrate meta-commands`

---

## Loop B — `/commands` generated reference (+ `/help` alias)

### Goal

Render the registry catalog as a `/commands` reference and make `/help` an alias.

### `/commands` behavior

- Lists every registered command.
- Shows name, aliases, and one-line summary.
- Groups by category if categories are present; otherwise alphabetical.
- Works on CLI, Telegram, and Matrix.

### `/help`

- Removed from the hardcoded help list in `meta.py`.
- Registered as an alias of `/commands`.

### Tests

- `/commands` contains every registered command (drift guard).
- `/help` output equals `/commands` output.
- Renders on each platform path without formatting errors.

### Commit message

`feat(commands): add /commands reference and alias /help to it`

---

## Loop C — `/tour` narrated walkthrough

### Goal

Add a curated, no-action-gated tour of Hestia's capabilities.

### Commands

- `/tour` — start the tour from step 1.
- `/continue` — advance one step.
- `/endtour` — clear the active tour cursor.

### State

- Cursor keyed by `(conversation_id, platform_user_id)`.
- Stored in existing per-conversation state storage.
- Ephemeral: a fresh `/tour` restarts from step 1.

### Steps

A static list of ~6–10 steps, each returning curated prose. Each step should surface one or more major commands/capabilities. Fast path: static text, no inference turn.

### Group-room behavior

- `/tour` in a group room does not start; replies DM-only.
- `/continue` and `/endtour` outside an active tour reply "no tour running".

### Tests

- `/tour` followed by repeated `/continue` walks every step and terminates cleanly.
- `/endtour` mid-tour clears the cursor; a later `/continue` reports no active tour.
- A second `/tour` restarts from step 1.
- In a multi-user room, `/tour` does not start.
- Drift guard: every major command/capability appears in at least one step.

### Commit message

`feat(commands): add /tour narrated walkthrough`

---

## Handoff

After the arc completes:

- Update `docs/development-process/kimi-loop-log.md`.
- Write/update handoffs for each loop.
- Add a short ADR for the registry design.
