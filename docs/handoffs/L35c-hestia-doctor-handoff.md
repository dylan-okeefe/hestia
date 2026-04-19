# L35c Handoff — `hestia doctor` command

## What shipped

New `hestia doctor` command with nine read-only health checks.

## Files changed

- `src/hestia/doctor.py` (new)
- `src/hestia/app.py` — `_cmd_doctor`
- `src/hestia/cli.py` — `doctor` command registration
- `tests/unit/test_doctor_checks.py` (new)
- `tests/cli/test_doctor_command.py` (new)

## The nine checks

1. **python_version** — `sys.version_info >= (3, 11)`
2. **dependencies_in_sync** — `uv pip check` (read-only, 10s timeout)
3. **config_file_loads** — smoke test that `app.config` is present
4. **config_schema** — placeholder; returns ok until `schema_version` is defined
5. **sqlite_dbs_readable** — `PRAGMA integrity_check` on the SQLite file
6. **llamacpp_reachable** — `GET /health` with 2s timeout; skipped when no `base_url`
7. **platform_prereqs** — validates credentials for enabled platforms (Telegram, Matrix, Email)
8. **trust_preset_resolves** — verifies `trust.preset` matches a known name
9. **memory_epoch** — checks `memory.epoch_path` exists and parses as `int`

## CLI usage

```bash
hestia doctor          # Unicode ✓/✗ markers
hestia doctor --plain  # ASCII [ok]/[FAIL] markers
```

Exit code is `0` when all checks pass, `1` if any fail.

## Design decisions

- **Read-only by contract.** No check writes state. `uv pip check` is a read operation.
- **Each check returns `CheckResult`.** Nothing raises into `run_checks`.
- **No auto-fix logic.** That is L39 (deferred until after dogfooding).
- **No schema-migration scaffolding.** Also L39.
- **No `pyproject.toml` bump.** Version stays at 0.8.0.

## Test coverage

- 20 unit tests (green + red paths for each check)
- 4 CLI end-to-end tests via `CliRunner`
- Suite totals: **777 passed, 6 skipped**

## Deferred work

- L39: auto-fix suggestions, `hestia upgrade`, config `schema_version` field, `memory.epoch_path` formal config
