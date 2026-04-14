# Hestia — L13 Handoff Report

**Date:** 2026-04-13  
**Branch:** `feature/l13-scheduler-matrix-cron`  
**Loop:** L13

---

## Summary

Delivered CLI session binding for scheduled tasks (`--session-id`, `--platform`, `--platform-user`) and comprehensive scheduler + Matrix delivery tests using a fake adapter. Confirmed destructive tools remain denied on scheduler ticks.

---

## What changed

### CLI: `hestia schedule add`

- **`src/hestia/cli.py`** — `schedule add` now accepts:
  - `--session-id <id>`: bind task to an existing session (validated to exist)
  - `--platform <name> --platform-user <user>`: get or create a session for the given platform pair
- Default behavior unchanged: binds to `cli` / `default` session when no binding flags are provided.
- Mutual exclusion: `--session-id` cannot be combined with `--platform` / `--platform-user`.
- Output now prints the bound `Session:` line for clarity.

### Tests

#### Unit tests — CLI scheduler

- `tests/unit/test_cli_scheduler.py` — added:
  - `test_add_with_session_id`: creates a session via `SessionStore`, then binds a task to it
  - `test_add_with_platform_and_platform_user`: creates a task bound to `matrix` / `!test-room:matrix.org`
  - `test_add_rejects_session_id_with_platform`: validation of mutually exclusive flags
  - `test_add_rejects_missing_session_id`: non-existent session ID is rejected
  - `test_add_rejects_platform_without_platform_user`: incomplete pair is rejected

#### Unit tests — scheduler + Matrix

- `tests/unit/test_scheduler_matrix.py` — new file covering:
  - `test_one_shot_delivers_to_matrix_room`: one-shot task bound to a Matrix session routes response through a fake `MatrixAdapter`; message is delivered to the correct room ID
  - `test_cron_task_advances_next_run`: cron task fires, `next_run_at` advances, task stays enabled
  - `test_scheduler_skips_delivery_when_session_not_matrix`: callback captures response but skips Matrix adapter when session platform is not `matrix`
  - `test_scheduler_tick_records_error_for_denied_tool`: scheduler tick records turn error when a destructive tool is denied (no `confirm_callback`)
  - `test_scheduler_tick_sets_scheduler_tick_active_flag`: verifies `scheduler_tick_active` context var is `True` during tick execution
  - `test_task_can_be_deleted_after_run`: teardown via `scheduler_store.delete_task` works after execution

---

## Quality checks

| Check | Result |
|-------|--------|
| `uv run pytest tests/unit/ tests/integration/ -q` | **466 passed**, 2 skipped (`matrix_e2e`) |
| `uv run ruff check src/ tests/` | clean |
| `uv run mypy src/hestia/cli.py tests/unit/test_cli_scheduler.py tests/unit/test_scheduler_matrix.py` | clean |

---

## Carry-forward / open items

1. **Orchestrator semantics (carry-forward from L12):** After `DONE`, outer `except` in `process_turn` can still record `failure_store` for delivery errors — remains noisy; gate in a follow-up if needed.
2. **Runtime parity (optional):** `~/Hestia-runtime/config.runtime.py` still uses ad-hoc Telegram env; optional `MatrixConfig.from_env()` / `.matrix.secrets.py` for Matrix parity.
3. **aiosqlite thread warnings:** Pre-existing; no action needed.

---

## Next step

Cursor review → merge to `develop` → advance `KIMI_CURRENT.md` to L14.
