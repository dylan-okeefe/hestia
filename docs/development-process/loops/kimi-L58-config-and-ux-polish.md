# L58 — Config, UX & Timezone Polish

**Status:** Complete. Feature branch work; do **not** merge to `develop`
until v0.11 release-prep.

**Branch:** `feature/l58-config-and-ux-polish` (from `develop`)

## Goal

Address usability papercuts: timezone confusion, missing CLI commands, and
config module bloat.

## Scope

### §0 — Review cleanup from L58 §1–§2

**Status:** Complete.

- [x] `tests/unit/test_config.py`: Remove duplicate `test_unknown_fields_ignored` (F811)
- [x] `tests/unit/test_config.py`: Remove unused `_ConfigFromEnv` import (F401)
- [x] `tests/unit/test_config.py`: Fix import sort order (I001)
- [x] `scheduler.py`: Fix column width mismatch in `cmd_schedule_list` (`<20` → `<24`)
- [x] Strip redundant `+00:00 UTC` from timezone-aware datetime displays
- [x] Add missing `config_env.py` tests — `_ENV_KEY_OVERRIDES`, `_LEGACY_ALIASES`,
  `tuple` coercion, `dict` skipping, nested dataclass skipping, complex union
  fallback, `from_env(environ=None)` path, empty string for `Literal` containing `""`.
- [x] Trim `config.py` to <500 lines — achieved 427 lines by moving validators and
  error classes out.
- [x] Audit remaining timestamp displays — all command modules now use `_format_utc()`
- [x] Unify datetime formatting — created `_format_utc()` helper in `_shared.py`,
  replaced all manual `strftime + " UTC"` patterns

### §1 — _ConfigFromEnv extraction

**Status:** Complete in commit `93378f3`.

Move `_ConfigFromEnv` and `_coerce_env_value` from `config.py` to
`config_env.py` (new file). Add integration tests for the coercion path
(bad env var types, missing vars, list parsing).

### §2 — Timezone suffix on displayed timestamps

**Status:** Complete in commits `79831c2` and `5a2b973`.

All user-facing timestamp displays now include a UTC suffix via the unified
`_format_utc()` helper.

### §3 — Token usage visibility

**Status:** Complete in commit `feat(cli): add token usage visibility...`.

After a chat turn, token usage is displayed when `--verbose` is set. Added
`/tokens` REPL command to show token usage for the most recent turn.

### §4 — /status in REPL

**Status:** Complete in commit `f4d4c8b`.

Enhanced existing `/session` command to show:
- Session ID, Platform, Platform User, State, Temperature, Started time
- Slot ID and save path (when set)
- Context window and turn budget (from policy engine)

### §5 — hestia ask vs hestia chat clarity

**Status:** Complete in commit `ce9735b`.

Updated CLI help text and README:
- `chat` = "Interactive REPL (persistent session)"
- `ask` = "Single-shot query (no session persistence)"

### §6 — schedule list format

**Status:** Complete in commit `ce9735b`.

Promoted `description` to primary identifier in `hestia schedule list`.
Task IDs hidden behind `--verbose` flag.

## Acceptance

- [x] `config.py` under 500 lines. (427 lines)
- [x] All timestamp displays include timezone.
- [x] `/tokens` or `--verbose` shows token counts.
- [x] `/session` works in REPL with slot and budget info.
- [x] Tests for config env coercion (including `_ENV_KEY_OVERRIDES`, `_LEGACY_ALIASES`,
  `tuple` coercion, and `dict` skipping).

## Commits

| Commit | Description |
|---|---|
| `93378f3` | refactor: extract _ConfigFromEnv to config_env.py + add integration tests |
| `79831c2` | feat: add UTC suffix to user-facing timestamp displays |
| `0be636d` | fix: review cleanup for L58 §1–§2 |
| `56071fa` | docs: update L58 spec with §0 review findings + skill auto-continue policy |
| `e9cc899` | test: add missing config_env.py test coverage |
| `c7a865c` | refactor: trim config.py to <500 lines |
| `5a2b973` | refactor: unify all CLI timestamp displays via _format_utc helper |
| `feat(cli)` | feat(cli): add token usage visibility after turns and /tokens REPL command |
| `f4d4c8b` | feat: add slot info and context budget to /session REPL command |
| `ce9735b` | feat: clarify ask vs chat in help text; promote description in schedule list |

## Dependencies

None.
