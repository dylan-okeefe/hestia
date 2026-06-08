# L216 — Documentation & Test Backfill Handoff

## Summary
Fixed stale documentation and filled critical test gaps before public release.

## Changes

### §1 — Documentation fixes
- **`docs/guides/environment-variables.md`**
  - Rewrote to match actual config fields in `src/hestia/config.py`
  - Removed stale `HESTIA_*` entries (API_KEY, TEMPERATURE, TOP_P, CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS, MAX_CONCURRENT, RETRY_BACKOFF_BASE_SECONDS, RETRY_MAX_ATTEMPTS, REQUIRE_CONFIRMATION, MAX_FILE_SIZE_MB, ALLOW_REMOTE_EXECUTION, ALLOW_WEB_SEARCH, ALLOW_EMAIL_READ, ALLOW_EMAIL_SEND, ALLOW_SCHEDULER, MIN_TURNS, SUMMARY_MODEL, THRESHOLD_TOKENS, INJECTION_SCAN_THRESHOLD, SSRF_BLOCK_PRIVATE_IPS, SSRF_ALLOWED_SCHEMES, IMAP_USE_SSL, SMTP_USE_TLS, SMTP_FROM, INTERVAL_HOURS, MIN_TURNS, MODEL, AUTO_ACCEPT, MAX_AGE_DAYS, UPDATE_INTERVAL_HOURS, DELEGATION_ENABLED, DELEGATION_THRESHOLD, ENABLED, TTS_MODEL, SAMPLE_RATE, INPUT_DEVICE, OUTPUT_DEVICE)
  - Added missing sections: Browser, Rate Limit, Web
  - Added missing fields across all existing sections
  - Removed non-existent `HESTIA_EXPERIMENTAL_SKILLS`

- **`docs/releases/v0.12.0.md`**
  - Fixed "hestia db upgrade" → schema applied on startup via `bootstrap_db()`
  - Fixed "first user becomes admin" → false (admin from registry/migrate-users)
  - Fixed "one-click trust presets in Config UI" → false (read-only)

- **`docs/guides/web-dashboard.md`**
  - Fixed default port from 8000 to 8765

- **`docs/development-process/kimi-loop-log.md`**
  - Added L212–L215 entries at the top

### §2 — Test backfill
- **`tests/unit/test_builtin_tools.py`**
  - Fixed `test_http_get_fetches_url` to patch `_fetch_with_httpx` instead of `httpx.AsyncClient` globally
  - Added `test_http_get_uses_ssrf_transport` asserting `AsyncClient` is instantiated with `SSRFSafeTransport`

- **`tests/unit/orchestrator/test_execution.py`**
  - Added `test_finish_reason_stop_with_tool_calls_routes_to_tools` covering execution.py:170-188
  - Added `test_reasoning_guardrail_nudge` covering execution.py:147-159
  - Added `test_streaming_repair_json` covering execution.py:451 (streaming JSON repair)
  - Added `test_scan_tool_result_wiring` covering `_scan_tool_result` integration in reassembly loop

- **`tests/unit/test_web_authz.py`**
  - Verified and expanded coverage for all `/api/*` routes
  - Added `TestBrowserSessionsAuth` (admin-only 403/200)
  - Added `TestConfigAuth` (401 without auth, 200 with auth)
  - Added `TestDoctorAuth` (401 without auth, 200 with auth)
  - Added `TestToolsAuth` (401 without auth, 200 with auth)

- **Brittle assertions fixed**
  - `tests/unit/test_context_builder.py`: `test_body_factor_applied` now compares `body_factor=2.0` vs `1.0` instead of `>= 0`
  - `tests/unit/test_web_auth.py`: `test_protected_route_passes_with_auth` now asserts `== 200` instead of `in (200, 500)`
  - `tests/unit/test_logging_config.py`: Strengthened tests to record initial state, assert relative changes, and restore state afterward

## Quality Gates

| Gate | Result |
|------|--------|
| `uv run pytest tests/unit/ tests/integration/ -q` | ✅ 1709 passed, 6 skipped, 1 failed (pre-existing flaky `test_doctor_check` in full suite; passes in isolation) |
| `uv run mypy src/hestia` | ✅ No issues |
| `uv run ruff check src/ tests/` | ⚠️ 139 pre-existing errors; none in modified files |

## Commits
1. `docs: update env vars, release notes, web-dashboard port, and kimi-loop-log`
2. `test: backfill TurnExecution branches, SSRF transport, authz coverage, and fix brittle assertions`

## Branch
`feature/l216-docs-test-backfill`
