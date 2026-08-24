# ADR-052: Allowlist-only tool authorization for unattended channels

- **Status:** Accepted
- **Date:** 2026-08-23
- **Context:** The L222 capability gate evaluated tool requests at call
  time, but its `allow_list` input was advisory: nothing forced callers to
  supply one, so unattended channels (workflow, webhook, scheduler, email)
  effectively ran under deny-list semantics. The round-1 review (finding
  F5) identified four code paths that reached tool execution without a
  gate evaluation at all: policy-delegation `delegate_task`, workflow
  `tool_call` nodes, investigate nodes with inputs-shaped tool configs,
  and truncated-write recovery handlers. Separately,
  `TrustConfig.scheduler_*` flags only shaped which tools were
  *advertised*; at enforcement they were silently dead.

- **Decision:**
  1. **Registry-level chokepoint.** Every tool invocation goes through
     `ToolRegistry.call`, which requires a `ToolCallContext` (`tools/context.py`)
     carrying channel, actor, mode, optional allow-list, source workflow,
     and injection flag. Strict mode: no context means `TypeError`, and a
     registry with no bound gate refuses every call (`RuntimeError`) in
     both modes — there is no passthrough configuration. Denials raise
     `ToolBlockedError`; confirmation escalation raises
     `ToolConfirmationRequiredError`.
  2. **Single evaluation.** Exactly two modes exist. `enforce` evaluates
     the gate at the registry. `pre_gated` trusts a decision the caller
     already made for that invocation, bound to the tool name: a context
     built for tool X raises rather than authorizing tool Y, and a denied
     decision raises `ToolBlockedError`. Double-gating is prevented by
     construction.
  3. **Graph-derived authorization for workflows.** A workflow's stored
     `allow_listed_tools` set is computed exclusively by
     `derive_allowed_set` from the version's node graph (tool_call /
     investigate tools plus node-effect markers `node:http_request`,
     `node:send_message`). Clients cannot hand-edit it. Saving returns the
     derived set; activating diffs it against the stored grant and refuses
     with HTTP 409 + `{added, removed}` until the caller confirms with
     `confirm_allow_list_change=true`. Activation stores the new set
     before flipping the version active.
  4. **Activation authorizes effects.** Effect nodes are not registry
     tools; the executor refuses them unless their marker is present in
     the stored set, so an edited draft cannot exercise a new effect past
     an old grant.
  5. **Scheduler flags become real controls.**
     `DefaultPolicyEngine.unattended_allow_list` maps the four
     `scheduler_*` TrustConfig flags onto an explicit allow-list passed to
     the gate on SCHEDULER-channel turns.
  6. **Audited both ways.** The gate writes `capability_events` rows for
     ALLOW decisions on unattended channels (reason `allow_listed`) as
     well as denials and escalations.
  7. **Migration m011** backfills pre-L245 rows from their active
     version's derived set; only empty sets are touched, custom grants
     are never clobbered, and it is idempotent.

- **Consequences:**
  - **Breaking:** workflows saved before this change must be re-activated
    once; activation now requires confirmation whenever the derived
    authorization set changes. API clients calling `registry.call`
    without a context fail loudly.
  - Adding a tool or effect node to a saved workflow does nothing until
    the new version is activated and the diff confirmed — the intended
    friction for unattended authority.
  - The four F5 bypass paths are closed structurally (they route through
    gated dispatch / the registry), not by per-site checks that can rot.
  - `investigate` tool selection is config-only: trigger payloads can no
    longer choose which tools an investigation runs.
