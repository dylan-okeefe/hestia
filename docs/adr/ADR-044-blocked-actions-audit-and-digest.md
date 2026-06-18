# ADR-044: Blocked-actions audit events and scheduled digest

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** Hard-denying unattended destructive actions (ADR-042) is safe but
  silent. A legitimate workflow that needs a destructive tool would just fail to
  do its job with no signal, and an actual injection attempt would leave no
  trace the operator sees. An aggressive deny-by-default is only livable if
  nothing is lost, just deferred to a review (L223).

- **Decision:**
  1. The `CapabilityGate` writes a structured audit event
     (`CapabilityEventStore`, `persistence/capability_events.py`) on every deny
     or escalation: tool, scrubbed args, channel, originating workflow/trigger,
     and reason (`not_allow_listed` vs `injection_flagged`).
  2. A scheduled digest task (`blocked_actions/digest.py`, dispatched via the
     scheduler) delivers a summary to the operator's primary channel, default
     09:00 and configurable. Empty digests return `"SILENT"` and are skipped.
     Injection events are marked distinctly from policy denials.
  3. An on-demand summary tool (`tools/builtin/blocked_actions_summary.py`)
     answers "did anything get blocked" without waiting for the schedule.

- **Consequences:** Hard-deny becomes visible and tunable; the digest is the
  surface a future batched-notification system will plug into. A durable
  approval queue with workflow suspend-and-resume is deferred to a separate
  design (see `docs/roadmap/future-systems-deferred-roadmap.md`); it would apply
  only to legitimate policy gates, never to injection denials.

- **Related:** ADR-042, ADR-043, ADR-027; `persistence/capability_events.py`,
  `blocked_actions/digest.py`, `scheduler/engine.py`.
