# Hestia — L12 Handoff Report

**Date:** 2026-04-13  
**Branch:** `feature/l12-matrix-e2e-two-user`  
**Loop:** L12

---

## Summary

Delivered real-homeserver Matrix E2E tests gated by environment variables, with deterministic mock inference behind a test harness. Added optional programmatic tester driver and updated credentials documentation.

---

## What changed

### New test module

- `tests/integration/test_matrix_e2e.py` — two `@pytest.mark.matrix_e2e` tests:
  - `test_matrix_e2e_ping_pong`: sends "ping" from a `matrix-nio` tester client and asserts the bot replies "pong" via a canned `FakeInferenceClient` response.
  - `test_matrix_e2e_tool_visible_reply`: sends "what time is it?", mock inference returns a `current_time` tool call, and the bot replies after tool execution.
- Both tests **skip cleanly** when any required env var is missing.
- Uses a **test harness** (`MatrixAdapter` + `Orchestrator` with `FakeInferenceClient`) for determinism, while still exercising real Matrix `/sync` and `room_send` against a live homeserver.
- Memory teardown deletes any memories tagged `e2e_hestia_l12` after each test.

### New script

- `scripts/matrix_test_send.py` — standalone tester driver. Logs in with tester credentials, sends a message to `HESTIA_MATRIX_TEST_ROOM_ID`, and waits for a reply from the bot MXID.

### Docs update

- `docs/testing/CREDENTIALS_AND_SECRETS.md` — added the standardized L12 env var table (`HESTIA_MATRIX_HOMESERVER`, `HESTIA_MATRIX_USER_ID`, `HESTIA_MATRIX_ACCESS_TOKEN`, `HESTIA_MATRIX_TESTER_USER_ID`, `HESTIA_MATRIX_TESTER_ACCESS_TOKEN`, `HESTIA_MATRIX_TEST_ROOM_ID`, plus optional device IDs).

### Pytest marker registration

- `pyproject.toml` — registered `matrix_e2e: Real Matrix homeserver end-to-end tests (requires env vars)` under `[tool.pytest.ini_options].markers`.

---

## Quality checks

| Check | Result |
|-------|--------|
| `uv run pytest tests/unit/ tests/integration/ -q` | **455 passed**, 2 skipped (matrix_e2e) |
| `uv run ruff check tests/integration/test_matrix_e2e.py scripts/matrix_test_send.py` | clean |
| `uv run mypy tests/integration/test_matrix_e2e.py scripts/matrix_test_send.py` | clean |

---

## Carry-forward / open items

1. **Orchestrator semantics:** After `DONE`, outer `except` in `process_turn` still falls through to `failure_store.record` for delivery errors — noted as potentially noisy; gate in a follow-up if it becomes an issue.
2. **Runtime config:** `~/Hestia-runtime/config.runtime.py` still uses ad-hoc env for Telegram only. Optional: load `.matrix.secrets.py` or call `MatrixConfig.from_env()` for Matrix parity (not blocking tests).
3. **aiosqlite thread warnings:** Pre-existing housekeeping item; no action needed for L12.

---

## Next step

Cursor review → merge to `develop` → advance `KIMI_CURRENT.md` to L13.
