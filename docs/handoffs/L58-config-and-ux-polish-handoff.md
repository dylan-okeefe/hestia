# L58 — Config, UX & Timezone Polish

## Scope

Address usability papercuts: timezone confusion, missing CLI commands, and
config module bloat.

## Commits

| Commit | Section | Description |
|--------|---------|-------------|
| `93378f3` | §1 | Extract `_ConfigFromEnv` and `_coerce_env_value` to `config_env.py` |
| `79831c2` | §2 | Add UTC suffix to user-facing timestamp displays |
| `0be636d` | §0 | Review cleanup: fix duplicate test, unused import, column width mismatch, redundant `+00:00 UTC` |
| `56071fa` | §0 | Update L58 spec with review findings + skill auto-continue policy |
| `e9cc899` | §0 | Add missing `config_env.py` tests (overrides, aliases, tuple, dict, nested, union, literal) |
| `c7a865c` | §0 | Trim `config.py` to 427 lines by moving validators and error classes |
| `5a2b973` | §0 | Unify all CLI timestamp displays via `_format_utc()` helper |
| `6ac5fe4` | §3 | Add token usage visibility after turns and `/tokens` REPL command |
| `f4d4c8b` | §4 | Add slot info and context budget to `/session` REPL command |
| `ce9735b` | §5–§6 | Clarify ask vs chat help text; promote description in schedule list |

## Files changed

- `src/hestia/config.py` — thinned to 427 lines (was 727)
- `src/hestia/config_env.py` — **new** file with `_ConfigFromEnv` mixin and coercion helpers
- `src/hestia/core/validators.py` — **new** file with `validate_inference_model_name()`
- `src/hestia/errors.py` — added `EmailConfigError`
- `src/hestia/commands/_shared.py` — added `_format_utc()` helper
- `src/hestia/commands/admin.py` — UTC timestamps
- `src/hestia/commands/meta.py` — `/tokens`, enhanced `/session`
- `src/hestia/commands/reflection.py` — UTC timestamps
- `src/hestia/commands/scheduler.py` — UTC timestamps, `--verbose` flag for list
- `src/hestia/commands/style.py` — UTC timestamps
- `src/hestia/commands/tools.py` — UTC timestamps
- `src/hestia/commands/chat.py` — token usage display when verbose
- `src/hestia/cli.py` — updated help text, `--verbose` for schedule list
- `src/hestia/persistence/trace_store.py` — `session_id` filter on `list_recent()`
- `tests/unit/test_config_env.py` — 26 tests (was 18)
- `tests/unit/test_cli_meta_commands.py` — `/tokens` and `/session` tests
- `tests/unit/test_token_usage_display.py` — **new** token usage display tests
- `tests/unit/test_cli_scheduler.py` — verbose list test
- `README.md` — clarified `ask` vs `chat`

## Test coverage

- `config_env.py` coercion paths: fully covered (18 original + 8 new tests)
- `config.py` line count: 427 lines (<500 target)
- All CLI timestamp displays: unified through `_format_utc()`
- Token usage visibility: tested for verbose mode and `/tokens` command
- Schedule list format: tested default and `--verbose` modes

## Known issues / follow-ups

None. All acceptance criteria met.
