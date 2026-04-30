# L96 — `hestia audit run --strict` and Doctor/Audit Overlap

**Status:** Spec only
**Branch:** `feature/l96-audit-strict-doctor-overlap` (from `develop`)

## Intent

Two related issues:

1. **`hestia audit run` has no `--strict` mode.** In CI or health-check scenarios, you want audit to return a non-zero exit code if any check fails. Currently it reports results but always exits 0. Without `--strict`, audit can't be used as a CI gate or monitoring probe.

2. **`hestia doctor` and `hestia audit` overlap is confusing.** Both commands check system health, but their scopes and intended use cases aren't clear from `--help` text. A user running `hestia doctor` might think audit is redundant, or vice versa. The distinction should be explicit: `doctor` checks prerequisites (llama-server reachable, database writable, config valid), while `audit` checks runtime state and data integrity (orphan sessions, failed turns, tool permission drift).

## Scope

### §1 — Add `--strict` flag to `hestia audit run`

Find the `audit run` command definition (likely in `src/hestia/commands/` or `src/hestia/cli.py`).

Add a `--strict` / `-s` flag (default `False`). When enabled:
- Run all audit checks as normal
- If any check returns a failure/warning result, exit with code 1
- Print a summary line: `"STRICT: N checks passed, M failed"` or `"STRICT: all checks passed"`

The exit code behavior:
- `--strict` not set: always exit 0 (current behavior, backward compatible)
- `--strict` set, all pass: exit 0
- `--strict` set, any fail: exit 1

**Commit:** `feat(cli): add --strict flag to hestia audit run`

### §2 — Add a test for `--strict` behavior

Add a test that:
1. Runs `audit run` without `--strict` with a failing check — asserts exit code 0
2. Runs `audit run --strict` with a failing check — asserts exit code 1
3. Runs `audit run --strict` with all checks passing — asserts exit code 0

If mocking audit checks is complex, test at the CLI level using `CliRunner` (Click's test helper).

**Commit:** `test(cli): verify audit run --strict exit codes`

### §3 — Clarify doctor vs audit in help text

Update the `--help` descriptions for both commands:

For `hestia doctor`:
```
Pre-flight checks: verify that prerequisites are met (llama-server
reachable, database writable, config file valid, required directories
exist). Run this when setting up or after config changes.
```

For `hestia audit`:
```
Runtime health and data integrity: check for orphan sessions, failed
turn patterns, tool permission drift, and data consistency. Run this
periodically or in CI with --strict.
```

Find where these help strings are defined (click `@command` decorators or `help=` arguments) and update them.

**Commit:** `docs(cli): clarify doctor vs audit scope in help text`

## Evaluation

- **Spec check:** `hestia audit run --strict` exists, returns exit code 1 on failures, exit code 0 on success. Doctor and audit help text clearly distinguish their scopes.
- **Intent check:** A CI pipeline can use `hestia audit run --strict` as a gate — the exit code is meaningful. A new user reading `--help` can immediately understand when to use `doctor` vs `audit` without guessing.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. `hestia audit run` without `--strict` behaves exactly as before (exit 0 regardless of results).

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `hestia audit run --strict --help` shows the flag in help output
- `.kimi-done` includes `LOOP=L96`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
