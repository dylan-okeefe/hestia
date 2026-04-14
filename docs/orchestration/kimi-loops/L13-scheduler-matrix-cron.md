# Kimi loop L13 — Scheduler (cron + one-shot) with Matrix delivery

## Review carry-forward

- **Orchestrator semantics (non-blocking):** After `DONE`, outer `except` in `process_turn` can still record `failure_store` for delivery errors — noisy; gate in a follow-up if needed (L12 handoff).
- **Runtime parity (optional):** `~/Hestia-runtime/config.runtime.py` still ad-hoc Telegram env; optional `MatrixConfig.from_env()` / `.matrix.secrets.py` for Matrix parity.
- **Housekeeping:** aiosqlite thread warnings in pytest — pre-existing.
- **L12 tests:** Matrix E2E uses env-gated skips (`matrix_e2e`); maintain skip behavior when extending scheduler/Matrix tests.

**Branch:** `feature/l13-scheduler-matrix-cron` from **`develop`** (includes **L12**).

---

## Context

`hestia matrix` runs the **Scheduler** in-process; scheduled tasks deliver via **Matrix** when the task’s session is `platform=matrix` (`cli.py` scheduler callback).

Today **`hestia schedule add`** always binds new tasks to the **CLI** session (`get_or_create_session("cli", "default")`). That prevents attaching a cron job to a **Matrix** room session from the CLI.

---

## Goals

1. **Product fix (if not already possible):** Allow creating a scheduled task bound to a **given `session_id`** or to **`platform=matrix` + `platform_user=<room id>`** (minimal CLI extension: e.g. `--session-id` on `schedule add`, validated to exist and optionally must be `matrix`). **Alternative:** document internal `SchedulerStore.create_task` for tests only — prefer user-facing CLI if small.
2. **Tests:**
   - **One-shot** (`--at` soon): task runs once; **Matrix room** receives bot message (env-gated, or in-process with fake adapter if E2E too heavy).
   - **Cron:** use a **fast** cron (e.g. every minute) in a **short** test window **or** inject `next_run_at` via store in test — document flake avoidance.
   - **Policy:** confirm destructive tools remain **denied** on scheduler tick (`scheduler_tick_active` / headless path).
3. **Teardown:** delete/disable tasks after test (`schedule remove` or store API).

---

## Handoff

`docs/handoffs/HESTIA_L13_REPORT_<YYYYMMDD>.md` + `.kimi-done` `LOOP=L13`.

---

## Rules

Same pytest/ruff/mypy bar. Prefer fast tests; mark slow E2E clearly.
