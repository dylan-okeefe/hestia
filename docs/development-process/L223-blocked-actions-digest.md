# L223 — Blocked-actions digest

**Status:** Spec only. Feature branch work; do not merge to develop until release-prep merge sequence.
**Branch:** `feature/l223-blocked-actions-digest` (from `develop` after L222 merges)
**Depends on:** L222 (the `CapabilityGate` must emit structured audit entries on deny/escalate — decision #8)

## Goal

Deliver a scheduled daily digest of unattended actions the `CapabilityGate` denied or escalated, plus injection-detection events, so the hard-deny default (L222 decision #1) is visible and tunable rather than silent. This is what makes an aggressive deny-by-default safe to live with: nothing is lost, just deferred to a review.

## Review carry-forward

- *(none — new spec-driven arc)*

## Scope

### §1 — Blocked-actions store / query

Persist the gate's deny/escalate audit entries. Reuse the existing audit/egress store if it fits; otherwise add a small `blocked_actions` table.

**Fields:** `timestamp`, `tool`, `args` (scrubbed via the existing scrubber — no secrets/PII), `channel`, `originating_workflow_or_trigger`, `reason` (`not_allow_listed` | `injection_flagged`), `resolution` (`denied` | `escalated_confirm`).

**Query:** entries since a given timestamp, for digest assembly and on-demand lookup.

**Commit:** `feat(audit): persist gate deny/escalate entries for blocked-actions digest`

### §2 — Digest scheduled task

A built-in scheduled task that reads blocked-actions since the last digest and sends a summary to the operator's primary channel.

- Config: `notifications.blocked_digest_time` (default `09:00`), `notifications.blocked_digest_channel` (default the operator's primary platform).
- Skip entirely if there were no entries (no empty "nothing happened" digest).
- Mark injection-flagged entries distinctly; group the rest by workflow/trigger.
- Reuse the existing scheduler and platform adapters; do not build new delivery infrastructure.

**Commit:** `feat(notifications): scheduled blocked-actions digest`

### §3 — On-demand query

The operator can ask the agent "did anything get blocked" and get the same summary on demand (a read of the store), independent of the schedule.

**Commit:** `feat(tools): on-demand blocked-actions summary`

## Tests

- Gate deny/escalate writes an audit entry (scrubbed).
- Digest assembles entries since last run, skips when empty, marks injection entries distinctly.
- On-demand query returns the same data as the digest.

## Acceptance

- `uv run pytest tests/unit/ tests/integration/ -q` green
- `uv run mypy src/hestia` reports 0 errors
- `uv run ruff check src/ tests/` at baseline or better (line-length 120)
- `.kimi-done` includes `LOOP=L223`
- Manual: trigger a blocked workflow action, confirm it appears in both the digest and the on-demand query.

## Handoff

- Write `docs/handoffs/L223-blocked-actions-digest-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to the next queued item (or idle)

## Critical rules recap

- Do not merge or push without Dylan's okay.
- The digest is read-only over the audit store.
- Scrub args before storing; no secrets or PII in audit entries.
- Reuse the existing scheduler/adapters; no new notification infrastructure (the general batching/blackout-window system is a separate future feature).
