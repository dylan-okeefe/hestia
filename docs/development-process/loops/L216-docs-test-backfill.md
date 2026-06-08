# L216 — Documentation & Test Backfill

## Goal
Fix stale docs and fill critical test gaps before public release.

## §1 — Documentation fixes

Files to audit and fix:
- `docs/guides/environment-variables.md`
  - Many documented `HESTIA_*` fields don't exist in current `config.py` dataclasses.
  - Update to match actual config fields. Remove stale entries.
- `docs/releases/v0.12.0.md`
  - "hestia db upgrade" doesn't exist — schema is applied on startup via `bootstrap_db()`.
  - "first user to log in becomes admin" is false.
  - "one-click trust presets in Config UI" is false (read-only).
- `docs/guides/web-dashboard.md`
  - Says default port 8000; actual is 8765.
- `docs/development-process/kimi-loop-log.md`
  - Add L212-L215 entries.

## §2 — Test backfill

- `tests/unit/test_builtin_tools.py:450-466` — `test_http_get_fetches_url` patches
  `httpx.AsyncClient` globally, bypassing `SSRFSafeTransport`. Fix the patch to
  target the transport layer or add a separate test that asserts SSRF transport
  is actually used.
- TurnExecution quant-model branches — add tests for:
  - `finish_reason="stop" + tool_calls` path (execution.py:170-188)
  - Reasoning-guardrail nudge (:147-159)
  - Streaming `repair_json` (:451)
  - `_scan_tool_result` wiring
- `tests/unit/test_web_authz.py` — already expanded in L212; verify coverage
  is complete for all /api/* routes.
- Brittle assertions to fix:
  - `assert result.tokens_used >= 0` (asserts nothing meaningful about calibration)
  - `assert status_code in (200, 500)` (accepts 500 as success)
  - Private-attribute / log-string assertions

## Quality Gates
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff
Write `docs/handoffs/L216-docs-test-backfill-handoff.md`.
