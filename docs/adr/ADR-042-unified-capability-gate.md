# ADR-042: Unified CapabilityGate is the single trust/capability boundary

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** Trust was split across four mechanisms that did not agree:
  `TrustConfig` + `policy/default.py`, the workflow executor's own `_TRUST_CAPS`
  (which called `tool_registry.call` directly, bypassing the policy gate), and a
  `User.trust_preset` that was stored but never enforced. No single boundary
  that every tool-execution path had to pass existed (L222). This built on the
  capability labels from ADR-031 and the sender resolution from ADR-039.

- **Decision:**
  1. `CapabilityGate` (`policy/gate.py`) is the one boundary. Every execution
     path (orchestrator, workflow executor, scheduler, subagent delegation)
     builds a `CapabilityRequest` with a `Channel` and calls `check()` before a
     tool runs. The workflow executor's `_TRUST_CAPS` is removed.
  2. Channels are classified **trusted** (CLI, Telegram, Matrix, API) vs
     **unattended** (email, webhook, workflow, scheduler). A subagent inherits
     the delegating operator's trust.
  3. Effective trust precedence: `trust_overrides[sender]` → `User.trust_preset`
     → `HestiaConfig.trust.preset` → `auto_approve_tools`. Per-user trust is now
     actually enforced. The trust actor is the human sender (ADR-039), not the
     room.
  4. The destructive subset (`shell_exec`, `write_local`, `email_send`, plus
     `browser_login` and `delegate_task`) on an unattended channel is
     hard-denied unless explicitly allow-listed per workflow. No interactive
     confirmation is attempted on an unattended trigger.
  5. The gate emits a structured audit event on every deny or escalation
     (ADR-044). Confirmations are bound to the original requester.

- **Consequences:** Admin/diagnostic web routes were scoped at the same time
  (config/tools/doctor/audit require admin; traces/egress/memory are
  caller-scoped, admin sees all), and webhook secrets are redacted from
  `GET /api/workflows`. Injection-flagged escalation layers on top (ADR-043).

- **Related:** ADR-031, ADR-039, ADR-005, ADR-030; `policy/gate.py`,
  `policy/channel.py`, `policy/identity.py`, `workflows/executor.py`.
