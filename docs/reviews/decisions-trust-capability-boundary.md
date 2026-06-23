# Decisions — L222 Trust/Capability Boundary

**Status:** Resolved 2026-06-15. These are the answers to the "Decisions needed before implementation" section in `docs/development-process/L222-trust-capability-boundary.md`, plus two additions agreed during the decision pass (#3 generalized injection escalation, #8 audit emit). Implement against these.

1. **Unattended destructive tools (workflow / webhook / scheduler).** Hard-deny by default, with explicit per-workflow allow-listing as the only escape hatch. Do not attempt to deliver interactive confirmations to an unattended trigger.

2. **Subagent trust.** A subagent inherits the trust of the operator who delegated it, including destructive tools, EXCEPT the gate gates the destructive subset (`terminal`/`shell_exec`, `email_send`, `browser_login`) when the subagent's context contains injection-flagged content. Low friction in normal operation; gated at the moment injection is detected.

3. **Injection-triggered escalation, all channels (generalizes #2).** When any message currently in the model's context carries the injection annotation, the destructive subset escalates:
   - Attended/trusted channels (CLI, Telegram, Matrix operator): require confirmation, even under the developer preset.
   - Unattended channels (workflow, webhook, scheduler, subagent): deny.

   "Flagged context" means any in-context message bears the scanner's annotation, not only the immediately-preceding tool result. The `CapabilityGate` consults the injection signal; this is the mechanism that gives the currently annotate-only scanner a real boundary. Keep it "confirm" (one tap) rather than "deny" for the operator so a false positive is not a hard block. The scanner threshold may need tuning once real traffic is observed.

4. **Trust matrix.**
   - Trusted channels: CLI, Telegram, Matrix (the operator).
   - Unattended/untrusted channels: email, webhook, workflow, scheduler.
   - Subagent: inherits operator trust, subject to the injection gating in #2/#3.
   - Destructive capabilities: `terminal`/`shell_exec`, `write_local`, `email_send`, `browser_login`, `delegate_task`.
   - Under the developer preset, trusted channels auto-approve everything; unattended channels gate the destructive subset regardless of preset.

5. **`trust_overrides` precedence and migration.** Precedence is `trust_overrides[sender]` → `User.trust_preset` → `HestiaConfig.trust.preset` → `auto_approve_tools`. Existing room/chat-keyed overrides migrate to the resolved sender key where determinable; otherwise drop with a logged warning rather than silently applying a room override to a different sender.

6. **Admin / diagnostic route scoping (§6).** `config`, `tools`, `doctor`, `audit` require admin. `traces`, `egress`, `memory` are caller-scoped (each user sees only their own; admin sees all). None may return global data to arbitrary authenticated users.

7. **Confirmation delegation (§4).** Confirmations are bound to the original requester only. An admin may not approve another user's pending tool.

8. **Gate audit emit (new).** The gate writes a structured audit entry on every deny or escalation: tool name, arguments (scrubbed), channel, originating workflow/trigger if any, and reason (`not_allow_listed` vs `injection_flagged`). This feeds the L223 blocked-actions digest.
