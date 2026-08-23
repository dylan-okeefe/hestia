# L245 — Allowlist-only tool authorization + gate chokepoint (#44)

Working state tracker. Checkboxes updated per landed commit; this file is
the source of truth for resume-after-interrupt.

## Chunks

- [x] A. ToolCallContext + registry chokepoint + workflow migration + real-registry trust fixture + fail-closed + dedup constant removed.
- [x] A0. Allow-side auditing in gate.check for unattended channels (commit on feature/l245-gate-chokepoint).
- [ ] A. ToolCallContext + registry.bind_gate + call(..., context) enforcement (deny→ToolBlockedError; confirm→ToolConfirmationRequiredError; pre_gated passthrough) + AppContext binds gate + workflow executor/nodes migrated to contexts + fail-closed when gate missing + drop duplicate _GATED_NODE_TYPES + trust-fixture converted to a real gated registry + direct-call enforcement test.
- [ ] B. investigate tools: config-only selection (resolver drops inputs precedence); flip inputs-path tests to expect denial-by-absence (no tools resolved from inputs).
- [ ] C. Orchestrator dispatch passes pre_gated context (single evaluation preserved); meta-tool path threaded through.
- [ ] D. Policy-delegation delegate_task rerouted through the same gated dispatch (bypass (i) closed).
- [ ] E. Truncated-write recovery rerouted through gated registry.call (bypass (iv) closed); no system-context exemption.
- [ ] F. Strict mode: registry.call requires a context (legacy None fallback removed); sweep tests.
- [ ] G. Scheduler allow-list derived from TrustConfig flags via policy engine (flags become real controls).
- [ ] H. derive_allowed_set(nodes) incl. node-effect markers; save returns derived set; activate requires confirmation of changes (409 + diff); m011 backfill migration against an existing-db shaped fixture; _is_url_safe private-import cleanup in http_request.py.
- [ ] I. Frontend: diff-on-activate dialog wired to 409 flow.
- [ ] J. CHANGELOG breaking-change entry; REMEDIATION_SUMMARY/architecture notes; metrics refresh; card #44 → In Review.

## Rules
Tests-first per chunk; full gates green per commit; no push/merge without Dylan.
