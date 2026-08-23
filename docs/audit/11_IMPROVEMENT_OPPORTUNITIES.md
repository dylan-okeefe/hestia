# Improvement Opportunities — Hestia

**Audit date:** 2026-08-22 · The actionable backlog derived from this audit. Each item: problem → evidence → proposal → benefit / effort / risk / dependencies / systems.
Prioritized ordering lives in `12_PRIORITY_ROADMAP.md`; speculative/future ideas separated into `13_IDEAS_AND_FUTURE_DIRECTIONS.md`.

---

## A. Security & trust

### A1. Make ungated tool invocation impossible (registry-level enforcement)
- **Problem:** Four paths invoke tool handlers without CapabilityGate; `workflow.trust_level`/scheduler flags are dead controls. — **Evidence:** SEC-001/003/004 + gate map in `08_SECURITY_PRIVACY.md` §2.
- **Proposal:** ToolRegistry holds a gate reference at construction; `registry.call()` enforces unless caller passes an explicit audited system context (`SystemContext.INTERNAL_MAINTENANCE` etc.). Gate remains the decision engine; orchestrator keeps UX flow (confirmation prompts) but authorization can no longer be bypassed by construction.
- **Benefit:** eliminates the class permanently; makes trust_level/scheduler flags enforceable for real. **Effort:** M (2-4 d). **Risk:** medium — needs careful pass over internal callers (maintenance passes, compaction summarizer, recovery). **Dependencies:** none. **Systems:** tools/registry, policy/gate, workflows/nodes, orchestrator.

### A2. Memory store fail-closed everywhere
- **Problem/Evidence:** SEC-010 (`store.py:735`, delete/soft_delete/update/pin/mark_* unscoped).
- **Proposal:** require identity on all scoped methods (raise or scope-by-callers-context); deprecate legacy epoch builder path.
- **Benefit:** closes cross-user read/delete family. **Effort:** S–M. **Risk:** low — internal unscoped callers are few (maintenance uses explicit scopes already). **Systems:** memory/store, context/memory_epoch, web/routes/memory.

### A3. Login surface hardening bundle
- SEC-002 server-derived recipients; SEC-004 auth-gate roster endpoint; SEC-006 debug_login in posture guard; SEC-023 generic auth errors. **Effort:** S total. **Risk:** low. **Systems:** web/routes/auth, web/auth, app.py guards.

### A4. Browser SSRF completion
- **Problem/Evidence:** SEC-005 (two tools unchecked; redirects/subresources unvalidated), SEC-020 headed-login.
- **Proposal:** pre-flight on browser_get_json/browser_interact; post-navigation `page.url` validation + Playwright route interception aborting blocked ranges; record navigations to egress log (SEC-025).
- **Benefit:** closes metadata-exfil class via the highest-privilege tool family. **Effort:** M. **Risk:** medium (route interception latency; false positives on legit redirect chains). **Systems:** tools/browser/*, security/ssrf.

## B. Reliability & correctness

### B1. Session-lock lifecycle fix
- BUG-001. Waiter-aware prune or refcounted acquisition + interleaving regression test (test-first per house style). **Effort:** S. **Risk:** low. **Systems:** orchestrator/lock, engine, runners, scheduler probe.

### B2. Streaming honesty pair
- BUG-003 fake-stop + BUG-022 SSE-error blindness (+BUG-046 unclosed generator). Typed error on stall/error-chunks; visible truncation marker alternative if product prefers graceful degrade — but pick one deliberately. **Effort:** S–M. **Risk:** low. **Systems:** execution.py, inference.py, finalization user messaging.

### B3. Scheduler backoff & dispatch
- BUG-012 exponential backoff + max-attempts/disable-with-notification; BUG-030 bounded-concurrency dispatch + claim-before-fire. **Effort:** M. **Risk:** low-medium (catch-up semantics need a decision: skip vs run-once). **Systems:** scheduler/engine, persistence/scheduler.

### B4. Workflow execution lifecycle
- BUG-036/037/004/005 + BUG-041 test isolation: RUNNING row upfront with per-node appends; startup sweep to FAILED; duration ceiling; per-workflow mutex; self-trigger refusal; schedule-triggers registered as first-class scheduled tasks; is_test flag excluded from status aggregates.
- **Benefit:** converts the weakest subsystem from "appears broken" to observable+safe; enables future cancellation UI. **Effort:** L (1 wk). **Risk:** medium — migration for executions table; trigger registration changes. **Dependencies:** none blocking. **Systems:** workflows/*, scheduler, web/routes/workflows.

### B5. Persistence hygiene bundle
- BUG-007 expanding bindparams + shared WHERE-builder; BUG-008 WAL/busy_timeout/FK audit; PERF-005 messages index; BUG-067 timestamp normalizer adoption; retention jobs for 9 tables (start with traces/capability_events/maintenance_trace TTL = undo window + margin). **Effort:** M aggregate, independently landable pieces. **Risk:** low each. **Systems:** persistence/*, scheduler/cleanup.

### B6. Platform adapter contract extraction
- Divergence cluster (BUG-032/065/066, reset divergence, streaming gap): shared command parser, chunker, edit-rate-limiter, reset helper as base-class defaults. **Effort:** M–L. **Risk:** medium (behavior changes on Matrix are user-visible fixes). **Systems:** platforms/*.

### B7. Telegram concurrency
- BUG-006 enable concurrent_updates after B1 lands. **Effort:** XS. **Risk:** low (session lock carries correctness). **Systems:** telegram_adapter.

## C. Context & model efficiency

### C1. Delta tokenization cache
- PERF-003: per-message counts keyed by content hash; tokenize deltas only. **Benefit:** largest recurring hot-path saving; multiplies with iteration count. **Effort:** M. **Risk:** medium (cache-invalidation subtleties; existing cache design points the way). **Systems:** context/builder, core/inference.

### C2. Token accounting truthfulness
- PERF-004 include_usage on streams; BUG-079 write reasoning tokens; warn on calibration/model mismatch (PERF-015). **Effort:** S. **Risk:** low. **Systems:** inference, builder, finalization/traces.

### C3. History-window selector fix
- BUG-027 advance-to-j+1 + unit test with two tool calls; BUG-072 protected-message exclusion from dropped slice; re-validate after splice (BUG-028). **Effort:** S. **Risk:** low. **Systems:** context/history_window_selector, compressed_summary_strategy.

### C4. Maintenance robustness
- BUG-010 abort-merge-on-update-failure; BUG-026 per-pair judge try/catch; BUG-011 FTS5 escaping+catch; BUG-036? (no—workflow). **Effort:** S each. **Risk:** low. **Systems:** memory/maintenance/*, memory/store.

## D. Product & UX

### D1. Work-loss prevention set
- BUG-055 401-grace preserving drafts; BUG-056 toast-not-fullpage activate failure; BUG-057 cron preserve-on-custom; B14 JSON discard warning. **Effort:** S aggregate. **Risk:** low. **Systems:** web-ui hooks/pages.

### D2. Editor learnability
- UX-001 human node labels, node-title variable pickers, single interpolation dialect w/ correct auto-insert; read-only version view without dirty flag. **Effort:** M. **Risk:** low. **Systems:** web-ui editor components.

### D3. Execution observability surface
- Depends on B4: skipped/failed nodes with reasons, test-run badges/filter, simple version diff. **Effort:** M after B4. **Systems:** web-ui Workflows pages + routes.

### D4. Routing & refresh resilience
- Hash/history routing per page. **Effort:** S. **Risk:** low. **Systems:** App.tsx shell.

### D5. Effective-policy viewer
- Read-only panel showing per-channel gating/auto-approve/confirm requirements derived from live gate config. Makes the trust model legible without source access; also exposes dead controls once A1 lands. **Effort:** M. **Risk:** low. **Systems:** new route + page; policy introspection helper.

### D6. Defer button (ship stranded feature)
- Backend supports proposals.defer; client fn exists unused. One button + state refresh. **Effort:** XS. **Systems:** Proposals.tsx.

### D7. A11y bundle
- A1 modal focus/Escape/restore; A2 token contrast bumps; A3 keyboard-operable rows; A4 label; A5 reduced-motion; A6 non-color statuses. **Effort:** M aggregate, small diffs individually. **Risk:** low.

### D8. Consistency sweep
- Date formatting helpers everywhere; unified destructive-confirm component; loading/error states on Workflows/Config; terminology pass (Knowledge→Memories etc.). **Effort:** S–M. **Risk:** low.

## E. Frontend performance

### E1. Bundle split + dependency drop
- PERF-001/002: React.lazy per route; manualChunks reactflow; remove openui. **Effort:** S–M. **Risk:** low-medium (visual regression check). **Benefit:** ~60-70% initial payload cut.

## F. Developer experience

### F1. Restore green gates + CI wiring
- ruff --fix (27 auto) + remainder; mypy fixes; TS build fix; wire all four gates into CI blocking; pytest-timeout. **Effort:** S. **Risk:** low. **Highest leverage-per-effort in the audit.**

### F2. Whole-app dev reload profile
- Problem: only uvicorn hot-reloads; adapters/scheduler stale until restart. Proposal: `hestia serve --dev` supervising subprocesses with restart-on-file-change, or documented docker-compose-style split. **Effort:** M. **Risk:** medium (process supervision complexity). **Benefit:** iteration speed for the platform-layer work this audit recommends.

### F3. Policy-doc consolidation
- .cursorrules → AGENTS.md single source. **Effort:** XS.

### F4. Delete-list execution
- §2 of `10_MAINTAINABILITY_TECH_DEBT.md`. **Effort:** S aggregate. **Risk:** low (grep-guarded).
