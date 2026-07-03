# Audit findings — verified (2026-06-29)

Consolidated, code-verified findings from the general/security audit, plus the
low-cost workflow-engine wins that are worth doing regardless of product
direction. The larger workflow-platform ideas live separately in
`workflow-engine-roadmap.md`.

**Verification key:** *Confirmed* = checked in the source this pass.
*Consistent* = matches the code as I know it but not line-verified here.
*Calibrated* = confirmed, with a note that changes the severity or urgency.

**Framing that runs through the security items:** the fail-open auth, the
wildcard tool approval, and the best-effort SSRF/path checks are not bugs. They
are deliberate local-first, single-user defaults. They convert into genuine
criticals the moment this repo is a public template or an instance is
network-exposed. The work below is re-posturing from local-first to
public/multi-user, not fixing broken code. Kimi should treat it that way and not
half-apply the guards.

## Critical — before any public release or network exposure

### C1. Auth-disabled mode fails open
*Confirmed, calibrated.* `web/dependencies.py`: both `require_admin` and
`RequireOwner` `return` success when the caller is unauthenticated and
`auth_enabled` is False, so a network-exposed dashboard becomes an
unauthenticated admin console. **Calibration:** your `config.runtime.py` ships
`auth_enabled=True`, so your box is not currently an open console. This is a
latent default/template risk, most likely to bite a new user who runs the web
server with auth off. Fix: make auth-disabled loopback-only or startup-fatal
unless explicitly marked local/dev; never let owner/admin dependencies return
success just because auth is off.

### C2. Workflow webhook secrets leak, and workflow lists are not owner-scoped
*Confirmed, both halves.* `web/routes/workflows.py`: `list_workflows` calls
`workflow_store.list_workflows()` with no owner filter and returns every
workflow, and `_workflow_to_api` returns `trigger_config` wholesale (which
carries the generated webhook `secret`). This leaks cross-owner even with auth
fully on, so it is arguably worse than C1 in a multi-user setup. Fix: redact
secrets in all list/get responses, scope the list by owner unless admin, and
reveal a webhook secret only once on creation or through an explicit rotate flow.

### C3. Shipped runtime posture models dangerous production behavior
*Confirmed.* `config.runtime.py` combines `auto_approve_tools=["*"]`, developer
trust, shell/write capabilities, and `web.host="0.0.0.0"`. Even as a personal
config it is a bad public template. Ties to existing board card #14 (privatize
`config.runtime.py`); this audit independently re-finds it. Fix: gitignore the
runtime config, ship a sanitized `config.example.py`, and add a startup guard
that refuses wildcard tool approval on a non-loopback web host.

### C4. Security disclosure and docs are not public-ready
*Confirmed.* `SECURITY.md` line 15 still uses `security@example.com`, and
`docs/guides/security.md` covers mainly prompt-injection annotation, not the
trust model, auth model, filesystem/terminal risk, or deployment hardening. Fix:
real disclosure path plus a concise threat-model/hardening guide.

## High

### H1. Confirmation callback is shared mutable state
*Confirmed.* `AppContext.confirm_callback` is instance state set by
`set_confirm_callback` and read in `make_orchestrator`, so in multi-platform
`serve` the last setter wins and a later orchestrator or delegated subagent can
pick up the wrong platform's confirmation path. Fix: pass the callback explicitly
into `make_orchestrator()` and delegate-tool construction.

### H2. Persistence schema ownership is split
*Confirmed (seen this pass).* Some DDL is in `persistence/schema.py`, some in
store-level create methods, and migrations are additive runtime helpers. Loop A
is a live example: the topic tables landed in `schema.py` while the `is_global`
column and memory DDL live in `memory/store.py`, which produced migration
carry-forward. Fix: make one bootstrap path authoritative and register all table
owners through it.

### H3. AppContext is the central coupling point
*Consistent.* One class wires DB, stores, policy, tools, workflows, web,
scheduler, memory maintenance, and platform concerns. Fix: split composition into
a few service groups (core stores/events, agent runtime, platform runtime, web
runtime) behind a thin facade. Refactor, sequence after the security set.

### H4. Shutdown is not centrally owned
*Consistent.* `serve` cancels tasks and closes inference, but DB close,
event-bus draining, trigger-registry lifecycle, adapter cleanup, and active-turn
draining are not ordered. Fix: an ordered lifecycle: stop accepting work, drain
turns/events, stop adapters/scheduler/triggers, close DB/inference. Matters for
production reliability.

### H5. Web API and frontend types are too loose
*Consistent.* Many routes return `dict[str, Any]`; the frontend client returns
unvalidated `res.json()` with duplicated page-local types. Fix: Pydantic
request/response models on the backend, a shared typed API layer on the
frontend. Incremental.

### H6. Frontend data fetching is inconsistent
*Consistent.* `useApiQuery` is local-state only; pages use manual effects;
dropdowns refetch tools/users/platforms repeatedly. Fix: one fetching pattern
with caching/deduping, or extend the hook to cache by key.

### H7. Open-source onboarding is not honest yet
*Consistent.* README `<repo-url>`, `uv sync` not matching all feature needs,
local config not ignored, frontend tests absent from CI, deploy docs conflicting
with the runtime-migration story. Fix: quick-start by mode, ignore local config,
align migration docs, add frontend tests to CI, add project metadata.

## Medium

### M1. Workflow trust_level looks enforced but is not
*Confirmed. I would raise this above medium.* `Workflow.trust_level` is stored,
validated, and surfaced in API/UI, but `workflows/executor.py` never reads it;
authorization goes through the global capability gate. A security control that
appears enforced but is not is worse than an absent one. Fix: either enforce it
in the executor or remove it from the UI/API until it means something.

### M2. Filesystem and HTTP egress protections are local-first grade
*Confirmed, calibrated.* Path checks are resolve-before-open and the SSRF guard
acknowledges DNS-rebinding gaps, which matches what ADR-045 already documents as
best-effort. Fine for local-first; not robust internet-facing. Fix (only if
internet-facing becomes a real goal): fd-based no-symlink opens for file tools,
pin resolved IPs or route egress through a hardened proxy.

### M3. TurnExecution is large and central
*Consistent.* Tool loops, streaming, retries, timeout escalation, injection
handling, and policy all live in one module. It is tested but hard to reason
about. Fix: extract retry/timeout/tool-dispatch/streaming helpers, behavior
preserved. After the security/lifecycle items.

### M4. Web layer uses a global context singleton
*Consistent.* Explicitly single-worker; routes can reach full AppContext. Fix
(not urgent unless scaling the web server): FastAPI lifespan/app-state plus
dependencies exposing narrow service ports.

### M5. Knowledge.tsx carries too much
*Consistent.* Mixes identity selection, sessions, style, memories, topics,
modals, and destructive actions, and defaults to the first identity. Fix: add
identity selection, split into a data hook plus table/section/modal components.

## Nice polish

- Standardize destructive actions on the existing `ConfirmDialog` instead of
  `window.confirm`.
- Use the shared `Button` component consistently.
- Route-level code splitting for heavy SPA pages, if bundle size hurts.
- Replace operator-specific shipped persona content with a `SOUL.example.md`
  before public release.

## Workflow engine — cheap wins now

These four are small, improve debuggability you already hit with long-running
browser workflows, and are worth doing regardless of whether workflows ever
become a headline feature. The larger workflow architecture is in
`workflow-engine-roadmap.md`.

### W1. Record skipped nodes
Today a node whose incoming edges are inactive is silently `continue`d and never
recorded, so skipped branches vanish from the execution result. Emit a
`NodeResult` with `status="skipped"` instead. Removes a silent-skip class.
Affected: `workflows/executor.py`, `workflows/execution_store.py`.

### W2. Persist a running execution row
`executor.execute()` only writes the execution record at terminal points, so a
run that dies mid-flight leaves no trace and nothing can observe an in-progress
run. Write a `running` row at start with an execution id, update it to the
terminal status at the end. Affected: `workflows/executor.py`,
`workflows/execution_store.py`.

### W3. Cancel token for workflow runs
There is no cancellation for an in-flight workflow (confirmed absent for turns
too). Add a cancel token threaded into the executor loop and inference call so a
stuck browser workflow can be aborted, and persist `cancelled` as a terminal
status. Affected: `workflows/executor.py`, `core/inference.py`.

### W4. Write down the graph semantics (decision note, not code)
The executor already behaves a specific way: merge is "any incoming edge
active," independent branches run sequentially in topological order, condition
and llm_decision route by `source_handle`, and the `edge.condition` field on the
model is unused. Document this as the defined behavior and decide whether to
remove `edge.condition` or implement it. Cheap, prevents future confusion.
Affected: `docs/guides/workflows.md`, `workflows/models.py`.

## Suggested sequencing

1. C1-C4 as a pre-public-release hardening arc (plus M1 folded in, since a fake
   security control is a release blocker).
2. W1-W4 alongside, they are small and independent.
3. H1, H2, H4 next (correctness/reliability seams).
4. Everything else as normal backlog; the refactors (H3, M3, M4) after the
   security set so they do not churn code that is about to be hardened.
