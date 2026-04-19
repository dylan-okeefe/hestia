# L29 Handoff — Reliability surface, secrets hygiene, stale docs

**Branch:** `feature/l29-reliability-secrets`  
**Merged to:** `develop` (pending Cursor review)  
**Target version:** 0.7.3  

---

## What changed

### §1 — Reflection scheduler failure visibility
- `ReflectionScheduler` gained a `_failure_log` ring buffer (max 20) and `failure_count` counter.
- `ReflectionRunner` accepts an optional `on_failure` callback; stage-level failures (`mining`, `proposal`) are recorded before returning `[]`.
- `ReflectionScheduler.tick()` records `"tick"` stage failures for any unhandled exception.
- `hestia reflection status` now prints scheduler health (ok/degraded, failure count, last run, last errors) above the proposal counts.
- CLI `schedule_daemon` uses `app.reflection_scheduler` (created in `cli()`) instead of instantiating a new one locally.

### §2 — Style scheduler failure visibility
- `StyleScheduler` gained the same ring-buffer pattern (`_failure_log`, `failure_count`, `status()`).
- `hestia style show` prints a `Failures:` section beneath the profile when `status()["ok"]` is `False`.
- CLI `schedule_daemon` also ticks `app.style_scheduler` each minute.

### §3 — Visible warnings on missing personality / calibration
- `cli()` honors `HESTIA_SOUL_PATH` and `HESTIA_CALIBRATION_PATH` before resolving files.
- Missing `SOUL.md` emits a yellow `click.echo` warning to stderr + `logger.warning`.
- Missing `docs/calibration.json` emits the same.
- README quickstart documents the env-var overrides.

### §4 — Email password env var
- `EmailConfig.password_env: str | None = None` added.
- `EmailConfig.resolved_password` property prefers `os.environ[password_env]` if set, falls back to `self.password`, raises `EmailConfigError` if the env var is missing.
- `EmailAdapter._imap_connect` and `_smtp_connect` use `resolved_password`.
- `docs/guides/email-setup.md` rewritten to present the env-var pattern as primary.

### §5 — Web-search provider type narrowing
- `WebSearchConfig.provider` changed from `str` to `Literal["tavily", ""]`.
- Docstring updated; factory error message tightened.

### §6 — SECURITY.md refresh
- Supported versions table: `0.7.x` supported, `< 0.7.0` unsupported.
- New "Trust profiles" subsection summarising the four presets and confirmation flow.
- New "Egress audit" subsection with `hestia audit egress` example.
- New "Prompt-injection scanner" subsection explaining annotate-not-block and threshold tuning.
- Disclosure line points to GitHub Security Advisories.

### §7 — ADR consolidation
- Moved ADR-0014, 0015, 0017, 0018 from `docs/development-process/decisions/` → `docs/adr/`.
- Updated references in `README.md`, handoff docs, and `KIMI_CURRENT.md`.
- Added `docs/development-process/decisions/README.md` redirect note.

---

## Test summary

```
pytest tests/unit/ tests/integration/ -q
```

673 passed / 6 skipped / 0 failed (baseline held).

New tests:
- `tests/unit/test_reflection_scheduler_failures.py` (5 tests)
- `tests/unit/test_style_scheduler_failures.py` (3 tests)
- `tests/integration/test_cli_reflection_status.py` (2 tests)
- `tests/integration/test_cli_missing_soul_warns.py` (2 tests)
- `tests/integration/test_cli_env_override_paths.py` (2 tests)
- `tests/unit/test_email_config_password_env.py` (4 tests)

---

## Verification checklist

- [ ] `uv run pytest tests/unit/ tests/integration/ -q` → 673 passed / 6 skipped / 0 failed
- [ ] `uv run mypy src/hestia` → 0 errors
- [ ] `uv run ruff check src/hestia tests` → ≤ 243 errors
- [ ] `git grep -n "docs/development-process/decisions" -- ':!docs/development-process/kimi-loops/' ':!docs/development-process/kimi-loop-log.md'` → no matches
- [ ] `hestia reflection status` shows scheduler health on a fresh install
- [ ] `hestia style show` shows no failure section when clean

---

## Carry-forward

- Ruff baseline: 243 errors (unchanged from L28).
- Test baseline: 673 passed / 6 skipped.
- No blockers.
