# L245 — Allowlist-only tool authorization + gate chokepoint (#44)

Working state tracker. Checkboxes updated per landed commit; this file is
the source of truth for resume-after-interrupt.

## Chunks

- [x] A.ToolCallContext + registry chokepoint + workflow migration + real-registry trust fixture + fail-closed + dedup constant removed.
- [x] A0. Allow-side auditing in gate.check for unattended channels (commit on feature/l245-gate-chokepoint).
- [x] A. ToolCallContext + registry.bind_gate + call(..., context) enforcement (deny→ToolBlockedError; confirm→ToolConfirmationRequiredError; pre_gated passthrough) + AppContext binds gate + workflow executor/nodes migrated to contexts + fail-closed when gate missing + drop duplicate _GATED_NODE_TYPES + trust-fixture converted to a real gated registry + direct-call enforcement test.
- [x] B. investigate tools: config-only selection (resolver drops inputs precedence); flip inputs-path tests to expect denial-by-absence (no tools resolved from inputs).
- [x] C. Orchestrator dispatch passes pre_gated context (single evaluation preserved); meta-tool path threaded through.
- [x] D. Policy-delegation delegate_task rerouted through the same gated dispatch (bypass (i) closed).
- [x] E. Truncated-write recovery rerouted through gated registry.call (bypass (iv) closed); no system-context exemption.
- [x] F. Strict mode: registry.call requires a context (legacy None fallback removed); sweep tests.
- [x] G. Scheduler allow-list derived from TrustConfig flags via policy engine (flags become real controls).
- [x] H. derive_allowed_set(nodes) incl. node-effect markers; save returns derived set; activate requires confirmation of changes (409 + diff); m011 backfill migration against an existing-db shaped fixture; _is_url_safe private-import cleanup in http_request.py.
- [x] I. Frontend: diff-on-activate dialog wired to 409 flow.
- [ ] J. CHANGELOG breaking-change entry; REMEDIATION_SUMMARY/architecture notes; metrics refresh; card #44 → In Review.

## Rules
Tests-first per chunk; full gates green per commit; no push/merge without Dylan.

## Progress log

- 2026-08-23: A0–A committed (chokepoint core + allow-side audit).
- 2026-08-23: B (investigate config-only), C (orchestrator pre_gated),
  D (delegation gated — bypass (i) closed), E (recovery gated — bypass
  (iv) closed), F (strict context required), G (scheduler allow-map)
  all landed green (2,294 passing).
- 2026-08-23: H landed — derive_allowed_set + node-effect markers
  (node:http_request / node:send_message), save returns
  derived_allow_list, activate 409-diff + confirm_allow_list_change,
  executor refuses effect nodes without their marker (fail-closed),
  m011 backfill (empty sets only, idempotent, existing-db fixture),
  is_url_safe made public.
- 2026-08-23: I landed — ActivationConfirmationRequired (typed 409
  error) in api client; AllowListDiffDialog (+css+tests); hook parks
  changed activations in pendingActivation across all three activation
  paths (save-and-activate, toolbar activate, version panel).
- NEXT on resume: J — derive_allowed_set(nodes) incl. node-effect
  markers ("node:http_request" etc.), save returns derived set, activate
  requires confirmation of diff (409 flow), m011 backfill migration with
  an existing-db-shaped fixture test, _is_url_safe private-import
  cleanup in http_request.py. Then I (frontend diff dialog) and
  J (CHANGELOG breaking entry, docs notes, metrics refresh, card #44 →
  In Review).
