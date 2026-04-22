# L053: Scheduler Push Notifications

**Status:** Complete — merged to `feature/v0.10.1-pre-publication-prep`  
**Branch:** `feature/v0.10.1-pre-publication-prep`  
**Scope:** Allow scheduled tasks to push results to the user's platform (Telegram, Matrix, etc.)

---

## Design

### Problem
Scheduled tasks currently only log to stdout/journald. Users want Telegram push notifications when scheduled tasks complete.

### Solution
1. Add `notify: bool` to `ScheduledTask` (opt-in per task)
2. Create `PlatformNotifier` that can send messages to Telegram (and later Matrix) using platform configs
3. Wire notifier into `Scheduler._fire_task` — when a task with `notify=True` completes, the response is also sent to the session's platform user
4. Add `--notify` flag to `hestia schedule add`

### Why not store platform on the task?
The session already has `platform` and `platform_user`. Reusing session context avoids denormalization and migration complexity.

### Why a separate PlatformNotifier?
The scheduler daemon and platform bots (Telegram, Matrix) run as separate processes. The notifier creates lightweight send-only clients from config without needing the full adapter lifecycle.

---

## Files touched

- `src/hestia/persistence/schema.py` — add `notify` column
- `migrations/versions/` — Alembic migration
- `src/hestia/core/types.py` — add `notify` to `ScheduledTask`
- `src/hestia/persistence/scheduler.py` — CRUD updates
- `src/hestia/platforms/notifier.py` — new PlatformNotifier
- `src/hestia/scheduler/engine.py` — wire notifier into `_fire_task`
- `src/hestia/commands/scheduler.py` — `--notify` flag, display
- `src/hestia/cli.py` — `--notify` option on `schedule add`

---

## Test Plan

- `uv run pytest tests/ -q` — no regressions
- Manual: `hestia schedule add --cron "*/5 * * * *" --notify "say hello"` → verify Telegram message after task fires
