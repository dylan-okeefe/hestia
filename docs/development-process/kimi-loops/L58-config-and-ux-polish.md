# L58 — Config, UX & Timezone Polish

**Status:** In progress. Feature branch work; do **not** merge to `develop`
until v0.11 release-prep.

**Branch:** `feature/l58-config-and-ux-polish` (from `develop`)

## Goal

Address usability papercuts: timezone confusion, missing CLI commands, and
config module bloat.

## Scope

### §0 — Review cleanup from L58 §1–§2

Fix issues found during deep review (committed as `0be636d`):

- [x] `tests/unit/test_config.py`: Remove duplicate `test_unknown_fields_ignored` (F811)
- [x] `tests/unit/test_config.py`: Remove unused `_ConfigFromEnv` import (F401)
- [x] `tests/unit/test_config.py`: Fix import sort order (I001)
- [x] `scheduler.py`: Fix column width mismatch in `cmd_schedule_list` (`<20` → `<24`)
- [x] Strip redundant `+00:00 UTC` from timezone-aware datetime displays

Remaining gaps to close in this cleanup section:

1. **Add missing `config_env.py` tests** — `_ENV_KEY_OVERRIDES`, `_LEGACY_ALIASES`,
   `tuple` coercion, `dict` skipping, nested dataclass skipping, complex union
   fallback, `from_env(environ=None)` path, empty string for `Literal` containing
   `""`.
2. **Trim `config.py` to <500 lines** — currently 535 lines. Move validators
   (`validate_inference_model_name`) or collapse docstrings to hit target.
3. **Audit remaining timestamp displays** — Verify `cmd_schedule_show`, trace
   list commands, and platform adapters also show UTC. Add tests capturing
   `click.echo` output.
4. **Unify datetime formatting** — Decide whether to use existing
   `_format_datetime()` (local time) or a new `_format_utc()` helper. Currently
   both approaches exist.

### §1 — _ConfigFromEnv extraction

**Status:** Completed in commit `93378f3`.

Move `_ConfigFromEnv` and `_coerce_env_value` from `config.py` to
`config_env.py` (new file). Add integration tests for the coercion path
(bad env var types, missing vars, list parsing).

### §2 — Timezone suffix on displayed timestamps

**Status:** Partially completed in commit `79831c2`, cleaned up in `0be636d`.

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
- Tests for config env coercion (including `_ENV_KEY_OVERRIDES`, `_LEGACY_ALIASES`,
  `tuple` coercion, and `dict` skipping).

## Dependencies

None.
