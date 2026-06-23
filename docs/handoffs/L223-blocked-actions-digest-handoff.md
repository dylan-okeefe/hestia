# L223 — Blocked-actions digest handoff

**Branch:** `feature/l223-blocked-actions-digest`  
**Parent:** `feature/l222-trust-capability-boundary`  
**Status:** Implementation complete, acceptance green.  
**Do not merge without Dylan's okay.**

## What changed

Implemented the blocked-actions digest spec from `docs/development-process/L223-blocked-actions-digest.md`.

### L222 gate fix (folded in)
- Removed `Channel.SUBAGENT` from the injection-escalation trusted-channel branch in `src/hestia/policy/gate.py`.
- A destructive tool call on `Channel.SUBAGENT` with `injection_flagged=True` is now denied.
- Non-injection subagent calls still inherit operator trust and auto-approve under permissive presets.
- Added `tests/unit/policy/test_gate.py::TestCapabilityGate::test_subagent_injection_is_denied_non_injection_inherits_trust`.

### §1 — Blocked-actions store / query
- Reused the existing `CapabilityEventStore` audit table (`capability_events`) from L222.
- Added `CapabilityEventStore.list_since(since, limit=1000)` in `src/hestia/persistence/capability_events.py`.
- Arguments stored by the gate are already scrubbed for secrets (`scrub_inputs`).

### §2 — Digest scheduled task
- Added `NotificationsConfig` (`notifications.blocked_digest_time`, `notifications.blocked_digest_channel`) to `src/hestia/config.py` under `FeatureConfig`.
- Added `task_type` column to `scheduled_tasks` schema + runtime migration `m007_scheduled_task_type`.
- Added `BlockedActionsDigest` service in `src/hestia/blocked_actions/digest.py`:
  - `query(since)` — read-only lookup over the audit store.
  - `format_digest(events)` — groups by workflow/trigger, marks injection-flagged entries distinctly, returns `None` for empty input.
  - `send_digest_for_task(task)` — uses the task's `last_run_at` as the window start.
  - `ensure_blocked_digest_task(...)` — creates or updates a daily digest scheduled task.
- Extended `Scheduler` in `src/hestia/scheduler/engine.py` to route `task_type == "blocked_digest"` tasks through the digest service instead of the orchestrator.
- Wired `app.blocked_actions_digest` into `Scheduler` constructors in `src/hestia/platforms/runners.py` and `src/hestia/commands/scheduler.py`.

### §3 — On-demand query tool
- Added `blocked_actions_summary` tool in `src/hestia/tools/builtin/blocked_actions_summary.py`.
- Registered in `AppContext.register_tools`; bound to `app.blocked_actions_digest`.
- Default lookback window is 24 hours.

### §4 — Tests
- `tests/unit/blocked_actions/test_digest.py` — digest formatting, query windows, `send_digest` silence, cron conversion, task upsert.
- `tests/unit/scheduler/test_blocked_digest_task.py` — scheduler routes `blocked_digest` tasks to the digest service and skips empty (`SILENT`) results; `chat` tasks still use the orchestrator.
- `tests/unit/tools/test_blocked_actions_summary_tool.py` — on-demand tool returns summary or empty-window message.
- Existing `tests/unit/policy/test_gate.py` updated for the L222 subagent fix and async-generator fixture typing.

### Deferred work
- Approval queue / workflow suspend-and-resume is **not** in this branch. A one-line stub was added to `docs/roadmap/future-systems-deferred-roadmap.md` (Tier A) for post-0.14 design.

## Acceptance

```bash
uv run pytest tests/unit/ tests/integration/ -q
# 1946 passed, 6 skipped

uv run mypy src/hestia
# Success: no issues found in 205 source files

uv run ruff check src/ tests/
# 68 errors (all pre-existing; all files touched by this loop are clean)
```

## Spec/decision item accounting

| Item | Status |
|------|--------|
| §1 Blocked-actions store / query | done |
| §2 Digest scheduled task | done |
| §3 On-demand query tool | done |
| L222 subagent injection fix | done |
| Deferred approval-queue/suspend-resume stub | done |

## Known issues / notes

- `tests/smoke/` includes environment-dependent tests requiring a live inference server; they were not part of the acceptance gate.
- The branch should merge to `develop` only after L222 lands, per the release-prep sequence.
- Empty digests return `"SILENT"` so the scheduler's notify path skips them.
