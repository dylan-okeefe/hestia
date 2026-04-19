# Kimi loop L35c — `hestia doctor` command (read-only health checks)

## Hard step budget

≤ **5 commits**, ≤ **2 new test modules**, scope strictly limited to the listed files. Stop after handoff commit; write `.kimi-done`; push; exit.

This is the largest of the four L35 mini-loops. Stay disciplined: nine checks, one helper module, two file integrations, two test files. Do not extend scope to auto-fix logic, `hestia upgrade`, or schema-migration scaffolding — those are L39 (deferred until after dogfooding).

## Review carry-forward

From L35a + L35b (assume both green-merged ahead of this loop):

- Test baseline: **≥ 750 passed, 6 skipped** (L34 + L35a + L35b new tests).
- Mypy 0. Ruff 44.
- `_cmd_policy_show` now derives from registry/config — pattern to follow if you need to inspect tool-registry state from inside `doctor`.

From `docs/development-process/reviews/v0.8.0-pre-release-plan.md` §4:

- `hestia doctor` is the **first line of defense** during the dogfooding week. When Dylan's husband says "it's not working," doctor is the one command Dylan asks him to run before anything else.
- `doctor` is **read-only**. No mutation, no auto-fix. `hestia upgrade` (L39, deferred) is where fixes live.

**Branch:** `feature/l35c-hestia-doctor` from `develop` post-L35b.

**Target version:** **stays at 0.8.0**.

---

## Scope

### §1 — `src/hestia/doctor.py` (new module)

Public surface:

```python
@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str  # short human-readable; multi-line OK; "" if ok and trivial


async def run_checks(app: CliAppContext) -> list[CheckResult]:
    """Run all health checks against the live app context. Order matters
    only insofar as later checks depend on earlier ones being green
    (e.g. config-loaded before db-readable). Each check is independent
    and never raises; failures are returned as CheckResult(ok=False, ...).
    """


def render_results(results: list[CheckResult], *, plain: bool = False) -> str:
    """Format results for terminal output. Symbols ✓/✗ unless plain=True,
    then [ok]/[FAIL]. Returns the full multi-line string."""
```

Each check is a private async function `_check_<name>(app: CliAppContext) -> CheckResult`. `run_checks` is a flat list — no class hierarchy, no plugin registry. Nine functions:

1. **`_check_python_version`** — `sys.version_info >= (3, 11)`. Detail on failure: `"Python {got}; need 3.11 or newer"`.

2. **`_check_dependencies_in_sync`** — Run `uv pip check` via `subprocess.run([..., "uv", "pip", "check"], capture_output=True, timeout=10)`. Ok if exit 0 and empty stdout. On failure, return the first 5 lines of stdout as detail. If `uv` is not on PATH, return `ok=False, detail="uv not found on PATH; cannot verify dependency sync"`.

3. **`_check_config_file_loads`** — Already loaded via `app.config`. So this check just verifies `app.config is not None` and surfaces the path it was loaded from (`app.config_source` if such an attribute exists, else `"<config object provided>"`). For an out-of-process invocation (which is what doctor is), the load already happened during `make_app`; if it had failed, the CLI wouldn't be running. So this check is mostly a smoke test. **Keep it** — its absence will be noticed when something else fails subtly.

4. **`_check_config_schema`** — If `app.config` has a `schema_version` attribute, compare against the current. Verify with `git grep -n schema_version src/hestia/config.py`. If the field doesn't exist today, the check returns `ok=True, detail="config schema_version not yet defined; pre-0.8.1 config"` and a `# TODO(L39)` comment in code.

5. **`_check_sqlite_dbs_readable`** — For each path in `(app.config.persistence.session_db_path, app.config.persistence.trace_db_path, app.config.persistence.artifact_db_path)` (verify field names — they may be `db_path` on different stores; use `app.session_store._db_path` etc. if necessary), open via `sqlite3.connect(path)` and run `PRAGMA integrity_check`. Ok if all three return `"ok"`. Detail on failure: per-db status, multi-line.

6. **`_check_llamacpp_reachable`** — If `app.config.inference.base_url` is set, do `httpx.get(f"{base_url.rstrip('/')}/health", timeout=2.0)`. Ok if exit 200. On timeout: `ok=False, detail="llama.cpp at {base_url}/health did not respond within 2s"`. On connection error: `ok=False, detail="cannot connect to llama.cpp at {base_url}"`. **Skip** the check (return `ok=True, detail="(no inference base_url configured)"`) if `base_url` is empty/None.

7. **`_check_platform_prereqs`** — For each enabled platform on `app.config.platforms` (Telegram, Matrix, email):
   - Telegram: env var or config field `bot_token` non-empty.
   - Matrix: homeserver URL set, user_id set, access_token OR (user + password OR `password_env` resolves).
   - Email: IMAP host + port + username set, AND password OR `password_env` resolves.
   Aggregate one `CheckResult` per platform that is **enabled** (skip disabled ones — they're not failures). Detail multi-line for the failing platforms.

8. **`_check_trust_preset_resolves`** — If `app.config.trust.preset` is set, verify it matches a known preset name. Use the existing trust-preset constants (`git grep -n PRESETS src/hestia/policy/`). If unset, ok with detail `"using custom trust config (no preset name)"`.

9. **`_check_memory_epoch`** — `app.config.memory.epoch_path` (verify field) exists, file is readable, contents parse as `int`. Ok if so. On any failure: `ok=False, detail="<path>: <reason>"`.

Each check **must catch its own exceptions** and return a CheckResult. `run_checks` itself never raises. If a check has an uncaught bug, that's a test gap — fix it as part of this loop.

### §2 — `_cmd_doctor` in `app.py`

Add at the end of the `_cmd_*` block (around the existing `_cmd_policy_show`):

```python
async def _cmd_doctor(app: CliAppContext, plain: bool) -> int:
    """Run health checks. Returns exit code (0 if all green, 1 if any fail)."""
    from hestia.doctor import run_checks, render_results

    results = await run_checks(app)
    click.echo(render_results(results, plain=plain))
    return 0 if all(r.ok for r in results) else 1
```

### §3 — `cli.py` registration

Import `_cmd_doctor` at the top of `src/hestia/cli.py` (alphabetical with the existing `_cmd_*` imports).

Add command at the end of the top-level commands:

```python
@cli.command()
@click.option("--plain", is_flag=True, help="Use ASCII [ok]/[FAIL] markers instead of ✓/✗.")
@run_async
async def doctor(app: CliAppContext, plain: bool) -> None:
    """Run a one-shot health check against the current Hestia install.

    Exits non-zero if any check fails. Read-only; never mutates state.
    Run this first when something seems wrong.
    """
    exit_code = await _cmd_doctor(app, plain=plain)
    if exit_code != 0:
        sys.exit(exit_code)
```

If `run_async` doesn't pass through option flags cleanly, look at how `init` or another `@click.option`-decorated command handles it and copy the pattern.

### §4 — Tests

`tests/unit/test_doctor_checks.py` (new) — green and red path for each check, 18 tests minimum:

- `test_python_version_ok` / `test_python_version_too_old` (monkeypatch `sys.version_info`)
- `test_uv_pip_check_ok` / `test_uv_pip_check_reports_drift` (monkeypatch `subprocess.run` to return non-zero)
- `test_uv_not_on_path` (monkeypatch `subprocess.run` to raise `FileNotFoundError`)
- `test_config_file_loads_ok` (smoke test on a normal `CliAppContext`)
- `test_config_schema_ok_when_field_missing` (assert it returns ok with the expected detail string when `schema_version` doesn't exist)
- `test_sqlite_dbs_readable_ok` (use temp SQLite databases)
- `test_sqlite_dbs_readable_reports_corruption` (write garbage bytes to one db file, assert `ok=False`)
- `test_llamacpp_reachable_skipped_when_no_base_url`
- `test_llamacpp_reachable_ok` (mock `httpx.get` to return 200)
- `test_llamacpp_reachable_timeout` (mock `httpx.get` to raise `httpx.TimeoutException`)
- `test_llamacpp_reachable_connection_error`
- `test_platform_prereqs_telegram_missing_token`
- `test_platform_prereqs_email_password_env_missing`
- `test_trust_preset_resolves_known`
- `test_trust_preset_resolves_unknown_preset_name` (e.g. `preset="not_a_preset"`)
- `test_memory_epoch_ok`
- `test_memory_epoch_missing_file`
- `test_memory_epoch_unparseable`

`tests/cli/test_doctor_command.py` (new) — end-to-end via `CliRunner`:

- `test_doctor_runs_and_exits_zero_on_clean_env` — mock the checks to all return ok; assert exit 0; assert all check names appear in output.
- `test_doctor_exits_one_when_any_check_fails` — patch one check to return `ok=False`; assert exit 1.
- `test_doctor_plain_uses_ascii_markers` — `invoke(cli, ["doctor", "--plain"])`; assert `[ok]` or `[FAIL]` in output, `✓` and `✗` absent.
- `test_doctor_default_uses_unicode_markers` — assert `✓` or `✗` in output.

Use `pytest.mark.asyncio` only if the existing test suite already uses asyncio fixtures for these patterns; otherwise stay sync via `CliRunner`.

---

## Commits (5 total)

1. `feat(doctor): introduce src/hestia/doctor.py with nine read-only checks`
2. `feat(cli): register hestia doctor command`
3. `test(doctor): green and red paths for all nine checks`
4. `test(cli): hestia doctor command end-to-end`
5. `docs(handoff): L35c hestia doctor`

Handoff doc is `docs/handoffs/L35c-hestia-doctor-handoff.md`, ≤ 80 lines, listing the nine checks, the `--plain` flag rationale, and explicitly noting that auto-fix and schema migrations are L39 (deferred).

---

## Required commands

```bash
uv run pytest tests/unit/ tests/integration/ tests/cli/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44. Pytest must end at **≥ 770 passed** (≥ 750 + 18 unit + 4 cli new tests) or higher.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L35c
BRANCH=feature/l35c-hestia-doctor
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- **Read-only.** No check writes anywhere. Even `_check_uv_pip_check` reads — `uv pip check` does not mutate.
- **Each check returns CheckResult.** Never raises.
- **No new dependency.** Use `httpx` (already in deps), `sqlite3` (stdlib), `subprocess` (stdlib).
- **No auto-fix logic.** That's L39.
- **No `pyproject.toml` bump.** No `CHANGELOG.md` edit.
- **Disabled platforms are not failures.** Only check what's enabled.
- Push and stop after `.kimi-done`.
