# Priority Roadmap — Hestia Audit

**Audit date:** 2026-08-22 · Derived from `07_BUGS_RELIABILITY.md`, `08_SECURITY_PRIVACY.md`, `06_PERFORMANCE.md`, `09_TESTING_QUALITY.md`, `11_IMPROVEMENT_OPPORTUNITIES.md`. IDs reference the register.
Sequencing principle: **make the ground truth trustworthy first (gates), close the trust-boundary hole, restore core concurrency invariants, then buy reliability/perceived-speed wins, then rebuild the workflow subsystem on solid footing, then polish product/UX.**

---

## Immediate (next 1–2 loops)

High-impact defects, data-loss/security exposures, and cheap unblockers:

| # | Item | Why now | Refs |
|---|------|---------|------|
| I-1 | **Restore green gates & wire CI** (ruff 49→0 incl. 27 auto-fix; mypy 7→0; fix TS build; pytest-timeout; web-ui build + mypy + ruff blocking) | Every other fix depends on trustworthy verification; currently all three gates are red on branch | TEST-001..006, BUG-049 |
| I-2 | **Registry-level gate enforcement** (route workflow tool_call/investigate nodes through CapabilityGate; make ungated paths structurally impossible; regression test: paranoid workflow × terminal denied) | Critical security hole contradicting ADR-042; webhook/chat-command reachable | SEC-001/003/004, ARCH-001 |
| I-3 | **Session-lock lifecycle fix** (waiter-aware prune/refcount) + interleaving test-first | Silent violation of per-session serialization invariant everything else relies on | BUG-001 |
| I-4 | **Memory fail-closed family** (list/delete/update/pin scoped-or-raise; retire legacy epoch builder path) | Cross-user read/delete family | SEC-010 |
| I-5 | **Login-surface bundle** (server-derived code recipients; auth-gate roster endpoint; debug_login posture guard; generic auth errors) | Anonymous-reachable primitives; trivial diffs | SEC-002/026/006/023 |
| I-6 | **Slot-eviction locking** (hold pool lock across save/erase or ownership tokens) | KV cross-contamination risk; real-world slot-op crashes documented | BUG-002 |
| I-7 | **Streaming honesty** (typed error for mid-stream stall; detect SSE error chunks; aclosing generator) | Silent truncation presented as success today | BUG-003/022/046 |
| I-8 | **Persistence quick fixes** (expanding bindparams in trace/failure stores; dialect-guard m006; parameterized timestamps) | User-facing 500s on filtered queries; PG path broken | BUG-007/009, BUG-088 cleanup |
| I-9 | **Frontend work-loss pair** (401-grace preserving drafts; activate failure = toast not full-page reload) | Users lose work to transient failures today | BUG-055/056 |
| I-10 | **Scheduler backoff** (exponential clamp to existing max + max-attempts/disable-with-notification) | Deterministically failing task hammers every 30 s forever | BUG-012 |

## Short term (following cycles)

| # | Item | Refs |
|---|------|------|
| S-1 | SQLite tuning + schema health: WAL/busy_timeout/FK audit; `(session_id, idx)` messages index; sessions last_active index; begin retention jobs (traces/capability_events/maintenance_trace TTL) | BUG-008, PERF-005/006, BUG-075 |
| S-2 | Telegram `concurrent_updates` (after I-3) | BUG-006 |
| S-3 | Workflow execution lifecycle milestone: RUNNING rows + node appends; startup sweep; duration ceiling; per-workflow mutex; self-trigger refusal; schedule-triggers as first-class scheduled tasks; require command/cron at activation | BUG-036/037/004/005/071 |
| S-4 | Test-run isolation (`is_test` sink excluded from status aggregates) | BUG-041 |
| S-5 | Context-window correctness: advance-to-j+1 pairing fix + two-tool-call unit test; protected-message exclusion from dropped slice; re-validate post-splice | BUG-027/072/028 |
| S-6 | Maintenance robustness batch: abort-merge-on-update-failure; per-pair judge try/catch; FTS5 escape-in-operator-mode + OperationalError catch + tag quoting; LIKE escaping | BUG-010/026/011/073/074 |
| S-7 | Voice/confirmation trust fixes: route voice turns through runner binding; plain-text fallback for confirmation prompts; group typing target | BUG-014/015/063 |
| S-8 | Browser SSRF completion: pre-flight on browser_get_json/browser_interact; post-goto URL validation + route interception; headed-login check; browser egress recording | SEC-005/020/025 |
| S-9 | Platform contract extraction: shared command parser (exact-token), chunker, edit-rate-limiter, reset helper | BUG-032/065/066, reset divergence |
| S-10 | Frontend bundle split + openui removal | PERF-001/002 |
| S-11 | Multi-user authorization gap batch: topic IDOR checks; dashboard scoping by owner/admin; owner_id server-derived; scheduler admin bypass | SEC-007/008/009, BUG-082, SEC-024 |
| S-12 | Token accounting truthfulness: stream include_usage; write reasoning tokens; calibration/model-mismatch warning | PERF-004/015, BUG-079 |
| S-13 | Product hygiene sprint: Defer button; date-format consolidation; unified destructive-confirm; loading/error states on Workflows/Config; Config Reveal honesty | U-series, BUG-083/084 |

## Medium term

| # | Item | Refs / deps |
|---|------|-------------|
| M-1 | Workflow cancellation + execution timeline UI (cancel endpoint, skipped-node results with reasons, test-run badges/filter, version diff) — depends on S-3/S-4 | UX-004 |
| M-2 | Delta tokenization cache in context builder | PERF-003 |
| M-3 | Effective-policy viewer (read-only per-channel gating/auto-approve panel) — natural companion to I-2 | D5, ARCH-001 |
| M-4 | Editor learnability pass: human node labels, node-title variable pickers, single interpolation syntax, loud unresolved-placeholder warnings + backend repr-safe serialization | UX-001, BUG-069/039 |
| M-5 | Retention completion for remaining tables + artifact GC scheduling + orphan-bin sweep + inline-store segmentation | PERF-010, BUG-artifacts |
| M-6 | Whole-app dev reload profile (`--dev` supervision) | F2 |
| M-7 | Terminal/file-tool hardening: output caps, timeout clamps, env scrubbing, atomic writes, streamed read_file | SEC-015, PERF-011a/b, tools F7 |
| M-8 | A11y bundle: modal focus/Escape, contrast tokens, keyboard-operable rows, labels, reduced-motion, non-color statuses | A1–A6 |
| M-9 | Delete-list execution + policy-doc consolidation (.cursorrules→AGENTS.md) + HandoffService single-instance | MAINT §2/§3 |

## Long term / optional

- **Action Registry → unified activity journal → durable executions → simulation mode → NL authoring** arc (ideas #1–#5 in `13_IDEAS_AND_FUTURE_DIRECTIONS.md`) — each stage independently valuable; sequence after S-3/M-1.
- Model routing profiles for judges (#7); mid-term memory layer (#8); household identity profiles (#9); chaos fakes + property tests as standing infrastructure (#11/#12); cost/quality dashboards (#14).
- Revisit Alembic (snapshot baseline or loud removal) once runtime migrations absorb the index work (S-1).

---

## Impact × Confidence ÷ Effort — top ~20

Scoring: Impact ∈ {Critical=10, High=8, Med=5}, Confidence ∈ {Confirmed=1.0, Highly likely=0.85, Potential=0.6}, Effort ∈ {XS=1, S=2, M=4, L=8}. Ties broken by dependency order (prerequisites first).

| Rank | Change | I×C÷E | Note |
|------|--------|-------|------|
| 1 | Restore green gates + CI wiring (I-1) | ~5.0 | multiplies value of everything else |
| 2 | Session-lock fix (I-3) | ~4.2 | Critical, Confirmed-by-inspection, small |
| 3 | Registry-level gate enforcement (I-2) | ~2.5 | Critical; larger effort but eliminates a class and unlocks trust_level/scheduler flags |
| 4 | Memory fail-closed family (I-4) | ~4.0 | High, confirmed, small |
| 5 | Login-surface bundle (I-5) | ~3.6 | four small diffs, one exposure class |
| 6 | Streaming honesty pair (I-7) | ~2.8 | ends "silent truncation" era |
| 7 | Persistence bindparams/m006/timestamps (I-8) | ~3.6 | real 500s today |
| 8 | Frontend work-loss pair (I-9) | ~3.6 | daily-driver trust |
| 9 | Scheduler exponential backoff (I-10) | ~3.4 | stops infinite hammering |
| 10 | SQLite pragmas + messages index + retention start (S-1) | ~2.7 | measured problems, durable headroom |
| 11 | Slot-eviction locking (I-6) | ~1.7 | high severity, medium effort |
| 12 | Telegram concurrent_updates (S-2) | ~3.4 (post-I-3) | biggest perceived-latency win |
| 13 | Context window selector fix (S-5) | ~2.7 | silent context loss in multi-tool turns |
| 14 | Maintenance robustness batch (S-6) | ~2.7 | protects nightly data integrity |
| 15 | Test-run isolation is_test (S-4) | ~2.7 | restores meaning of execution history |
| 16 | Cron triggers as real schedules (S-3 part) | ~1.7 | resurrects a feature users believe exists |
| 17 | Bundle split + drop openui (S-10) | ~2.4 | measured 800 KB gzip → ~⅓ |
| 18 | Voice/confirmation trust fixes (S-7) | ~2.4 | removes "works when typed, fails when spoken" |
| 19 | Browser SSRF completion (S-8) | ~1.6 | highest-privilege tool family |
| 20 | Workflow execution lifecycle milestone (S-3 whole) | ~1.5 | deliberately not penalized for size: unlocks cancellation/observability/product arc |

*Deliberately ranked lower despite genuine value:* a11y bundle (M-8, broad but incremental), effective-policy viewer (M-3, depends on I-2 semantics settling), delta tokenization (M-2, perf-only), dev-reload profile (M-6, DX comfort).
