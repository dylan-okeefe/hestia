# L58 — Config, UX & Timezone Polish

**Status:** Outline spec. Feature branch work; do **not** merge to `develop`
until v0.11 release-prep.

**Branch:** `feature/l58-config-and-ux-polish` (from `develop`)

## Goal

Address usability papercuts: timezone confusion, missing CLI commands, and
config module bloat.

## Scope

### §1 — _ConfigFromEnv extraction

Move `_ConfigFromEnv` and `_coerce_env_value` from `config.py` to
`config_env.py` (new file). Add integration tests for the coercion path
(bad env var types, missing vars, list parsing).

### §2 — Timezone suffix on displayed timestamps

All user-facing timestamp displays (scheduler list, trace list, etc.) must
include a timezone suffix ("UTC") or convert to local time if `timezone` is
configured.

### §3 — Token usage visibility

After a chat turn, show token usage (prompt tokens, completion tokens, total)
when `--verbose` is set or via a `/tokens` REPL command.

### §4 — /status in REPL

Add `/session` or `/status` to the chat REPL that shows:
- Session ID
- Slot ID and save path
- Temperature
- Context budget usage

### §5 — hestia ask vs hestia chat clarity

Update CLI help text and README to make the distinction explicit:
- `ask` = single-shot, no session persistence
- `chat` = REPL with persistent session

### §6 — schedule list format

Promote `description` to the primary identifier in `hestia schedule list`.
Hide `id` behind `--verbose`.

## Acceptance

- `config.py` under 500 lines.
- All timestamp displays include timezone.
- `/tokens` or `--verbose` shows token counts.
- `/status` works in REPL.
- Tests for config env coercion.

## Dependencies

None.
