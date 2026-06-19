# ADR-043: Injection-flagged content escalates destructive tools via the gate

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** ADR-017 made the injection scanner annotation-only, never
  blocking, to avoid a denial-of-service vector (crafted content that always
  trips the scanner would otherwise break legitimate tool chains). But with the
  developer preset auto-approving tools and unattended channels in play, an
  annotated-but-not-blocked injection could still talk the model into a
  destructive tool call. The annotation had no teeth (L222).

- **Decision:** Keep the scanner annotation-only for the model context (ADR-017
  stands), but feed the annotation into the `CapabilityGate` (ADR-042). When any
  message currently in context carries the injection annotation, the
  **destructive subset only** escalates:
  - Attended/trusted channels (CLI, Telegram, Matrix): require confirmation,
    even under the developer preset. A false positive is a single tap, not a
    hard block, which preserves ADR-017's anti-DoS rationale.
  - Unattended channels including subagent (no human to confirm): deny.

  Non-destructive tools and non-flagged turns are unaffected. "Flagged context"
  means any in-context message bears the annotation, not just the immediately
  preceding tool result.

- **Consequences:** The annotate-only scanner finally gates the dangerous subset
  without reintroducing the DoS risk it was designed to avoid. Injection denials
  are security events surfaced in the blocked-actions digest (ADR-044) and are
  never eligible for a future suspend-and-resume approval queue.

- **Related:** ADR-017, ADR-042; `policy/gate.py`, `security/injection.py`,
  `orchestrator/execution.py`.
