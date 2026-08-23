# Hestia Comprehensive Audit — Research Log

**Date:** 2026-08-22
**Auditor:** ox-alpha
**Worktree:** `/home/dylan/Hestia-runtime` (runtime branch; live-instance worktree)
**Constraints:** No production code changes. Output = `docs/audit/*`. Temporary diagnostics allowed if removed.

## STATUS: COMPLETE

All 14 deliverables written (`00`–`13` + this log, ~1,900 lines). Git status clean except `docs/audit/` (untracked output only) — zero production code modified.

### Completion checklist (per audit spec §23)
- [x] Every major subsystem inspected: platforms, persistence, workflows/engine+nodes+triggers, orchestrator/inference/slots, tools/policy/security/blocked_actions/artifacts, memory/context/reflection/style/scheduler/events, web layer/auth/browser-stream, frontend (all pages/hooks/styles), tests.
- [x] Both frontend and backend audited at code level.
- [x] Tests actually run: pytest 2272 passed/~260s ×4 deterministic; mypy 7 errors; ruff 49 errors measured.
- [x] Runtime behavior investigated on the live instance: service verified running (:8765 + llama-server :8001); DB pragmas measured (journal=delete, FKs=0); index inventory extracted from live schema; table row counts collected; crash forensics read.
- [x] Failure paths examined: streaming stalls, SSE errors, retries, crash windows, migrations, platform boot failures.
- [x] UX examined as a user as far as practical: live-service verification done; authenticated walkthrough not performed (2FA codes deliver to operator's personal chat — noted honestly in 05); UX findings are code-derived behavioral traces with confidence labels.
- [x] Performance investigated with measurements: production build output (2.74 MB single chunk), DB tuning state, index absence, data volumes/growth surfaces.
- [x] Test suite itself examined (invariants map, gaps, brittleness).
- [x] Security boundaries mapped exhaustively (gate enforcement map across all tool-invocation paths).
- [x] Git history used strategically (touch-count hotspots since Jan 2026).
- [x] Evidence vs speculation distinguished (Confidence labels throughout; register).
- [x] Strongest findings challenged: Critical gate bypass independently found by two agents AND verified by direct inspection (executor.py:366-378 / tool_call.py:54); lock race verified by direct inspection of asyncio.Lock semantics + call sites; SQLite findings verified against the live database rather than code claims.
- [x] Synthesis pass performed: five common root causes added to 01 §9; executive summary and roadmap reflect final synthesized understanding.


## Methodology

1. Reconstruct system from docs/ADRs/README, then verify against implementation.
2. Trace end-to-end flows (message → turn → tools → LLM → response).
3. Run tests/typecheck/lint; measure where practical.
4. Git history hotspot analysis.
5. Classify findings Confirmed / Highly likely / Potential risk.
6. Critical findings independently verified by direct inspection, not just agent claims.

## Phase 1: Orientation

- Repo: `src/hestia` (~41.7k LOC Python, 227 files), `web-ui` (React SPA + Playwright), `tests` (unit/integration/docs), `docs` (51+ ADRs), `migrations` (alembic reference-only).
- Largest backend files: orchestrator/execution.py (1738), telegram_adapter.py (1246), memory/store.py (1167), config.py (1012), app.py (820), cli.py (819).
- Process: solo operator (Dylan) + Kimi (implementer) + Claude (reviewer); loop specs, ADRs, quality gates pytest/mypy/ruff/web-ui build.
- Duplicate ADR number: two `ADR-051-*` files (external-tool-modules, two-tier-topic-scoped-memory).
- Runtime artifacts in worktree root are gitignored (dashboard.log 524KB, hestia.db, logs) — not repo hygiene issues in git.
- Key ADR themes: turn state machine w/ confirmation callback (012), SlotManager KV LRU (013), context resilience (014), Telegram HTTP/1.1 rate limiting (016), injection detection + egress audit (017), FTS5 memory not vectors (029), CapabilityGate unified trust boundary (042), per-session turn serialization (041), persistence store split (040), SSRF browser fetch (045), chunked file writes (046), compaction (047), session-end fact extraction (048), overnight maintenance (049), command registry (050), external tool modules (051).

## Phase 2: Subsystem audits via parallel exploration

### A. Platforms (telegram_adapter, matrix_adapter, cli_adapter, runners.py, email) — COMPLETE
Architecture mapped: TG private=user-id / group=chat-id sessions; Matrix room=sessions; Email→workflow events only; CLI REPL doesn't use CliPlatform. Confirmations: TG inline keyboards bound to requester; Matrix reply-pattern; 60s timeout, fail-closed GC. Streaming edits Telegram-only.

Findings (agent-reported, key ones):
- **RACE-01 (High)**: PTB sequential update processing; no `concurrent_updates` anywhere → one slow turn (LLM/tools/60s confirmation) blocks ALL chats/users. Head-of-line blocking.
- **RACE-02 (Med, Confirmed)**: voice handler calls orchestrator directly, skipping runner ContextVar binding → confirmations auto-denied during voice turns; channel misattributed as CLI (verified execution.py:1512 fallback).
- **RACE-03 (Med-High, Confirmed)**: workflow response interception matches only (platform, platform_user) — any allowed group member's next message swallowed as workflow answer up to 600s; inline `workflow:` buttons have NO allowlist check and resolve() has no identity binding (tool confirmations ARE requester-bound).
- **RACE-04 (Low)**: rate-limit error double-delivered (callback notify + raise PlatformError).
- **ERR-01 (Med)**: confirmation prompt renders raw tool JSON args with parse_mode="Markdown" no fallback → BadRequest on markdown metacharacters → gated tools fail spuriously.
- **ERR-02 (Med)**: edit_message fallback path duplicates all chunks or drops chunks[1:] on "message is not modified".
- **RES-02 (Med)**: email poller poison-message infinite redelivery every 30s, no dead-letter/backoff.
- **RES-03 (Med)**: email list fetches INTERNALDATE per UID (N round-trips); UID-as-epoch fallback bug.
- **RES-04 (Med-Low)**: send_draft unchecked COPY before \Deleted+expunge → draft loss if Sent copy fails.
- **COR-01 (Med-Low)**: Matrix startswith prefix matching → `/resetnow` triggers reset.
- **COR-02**: reset semantics diverge TG (LLM summary) vs MX (fixed marker).
- **COR-04 (Low-Med)**: Matrix initial sync failure kills entire serve process (no try around first sync; gather only suppresses CancelledError).
- **SEC-01 (Low-Med)**: allowlist `@username` entries never match (validation strips @, matching doesn't normalize) — fail-closed silent denial.
- **Matrix `_last_edit_times` never evicts** (unbounded growth vs TG prunes).
- Duplication: reset flow ×2, allowlist guard ×7 handlers in TG, 3 scheduler callback factories, edit-rate-limit logic ×2 adapters.
- Dead: delete_message, validate_matrix_room_alias, CliPlatform (tests only), TelegramConfig.fallback_ips/connect/read timeouts unused, request_token stored-never-read.

### B. Persistence — COMPLETE
Good: TOCTOU-safe get-or-create (partial unique index + IntegrityError retry), atomic compaction transaction, ErrorResolutionStore model citizen, secret scrubbing in capability_events, idempotent migration framework in single transaction.

Findings:
- **F1 (High, Confirmed)**: `IN :session_ids` expanding bindparam missing in trace_store + failure_store list queries → crashes when filtering by sessions (SQLAlchemy tuple binding).
- **F2 (High, Confirmed)**: No SQLite tuning: FKs OFF (default), no WAL, no busy_timeout → "database is locked" errors unhandled under concurrency.
- **F3 (High for PG)**: m006 uses pragma_table_info unguarded → PostgreSQL startup crash.
- **F4 (Med-High PG)**: raw-SQL isoformat string timestamps incompatible with asyncpg typed params.
- **F5 (Med)**: timestamp format fragmentation across stores (isoformat strings vs DateTime params) → wrong same-day comparisons in style/reflection schedulers.
- **F6 (Med)**: No retention for 9 tables (traces, capability_events, egress_events, turn records...); list_egress unbounded full-table dumps.
- **F7 (Low-Med)**: missing indexes for last_active_at ordering / stale-turn queries.
- **F8 (Med)**: DDL drift across 3 sources (schema.py, failure_store raw DDL, maintenance_trace_store) — constraint divergence legacy DBs vs fresh.
- F9-F13 (Low): Alembic stale vs schema (autogenerate would emit giant diff), bootstrap flag check-then-await race, scheduler backoff min(30,300)=30 dead code, get_turn_messages duplicated×2 zero-callers AND wrong (joins by session_id only), doc drift.

### C. Memory/Context/Reflection/Style/Scheduler/Events — COMPLETE
Good: tokenize cache design (keys exclude reasoning_content, bounded LRU 4096, content-hash keys), sequence validator loud system-notes on loop collapse, maintenance soft-delete+undo+trace posture honors ADR-049, scoping defense-in-depth on hot paths, scheduler checks session lock without awaiting (deadlock avoided).

Findings:
- **#1 (High)**: FTS5 sanitizer bypass — operator-containing queries skip escaping (`" NOT foo"` forms fall through); search() has no try/except; maintenance passes call search() with raw memory excerpts unprotected → OperationalError kills pass.
- **#2 (High, Confirmed)**: list_memories fails OPEN on missing identity (`if platform is not None and platform_user is not None:` adds scope clause only when both present) → cross-user read; delete()/soft_delete()/update() same fail-open; pin/mark_* have ZERO scoping. Contradicts fail-closed claim in search().
- **#3 (High)**: multi-tool-turn window selector advances i += len(pair_msgs) instead of j+1 → sibling tool result silently vanishes from context AND compressor visibility; assistant double-counted against budget.
- **#4 (High, Confirmed)**: failed scheduled tasks retry every constant 30s forever (min(_MIN,_MAX)=min(30,300)=30; "capped backoff" comment lies) → deterministically failing task hammers forever.
- #5 (Med): compression splice bypasses sequence validation; retry pop can orphan tool message → strict-template rejection at request time.
- #6 (High): merge/supersede ignore update() False return before soft-deleting losers → sanitizer-rejected merge loses information while recording success.
- #7 (Med): token calibration file records model name but loader ignores it → silent mis-budgeting after model swap.
- #8 (Med): epoch composition loads ENTIRE memory table per session start (no LIMIT; caps in Python after materializing).
- #9 (Med): reflection/style cron gate ±2-min window, volatile instance state, missed runs silent, restart can double-run.
- #10 (Med latent): EventBus.publish_nowait asyncio.run fallback destroys pending handler tasks.
- #11 (Med): tick loop holds lock during full process_turn (head-of-line blocking for due tasks); next_run written pre-dispatch → crash = skipped occurrence (at-most-once).
- #12 (Med): delete_memory tool does HARD DELETE contradicting soft-delete+undo posture.
- #13 (Low): naive-vs-aware datetime rows break epoch building/prune protection outside exception guards.
- #14 (Low): maintenance_trace grows unboundedly embedding merged-content blobs; no pruning job.
- #15-#18 (Low): LIKE wildcard non-escaping, tag quoting breaks MATCH, dropped-history includes protected msg over-reporting truncation, auth-code filter drops ANY 4-10 digit user message globally ("2026", port numbers vanish from history).
- #19 (Low-Med): reflection ships raw user-input summaries to LLM unscrubbed; scrub module exists but unused here; proposals persist indefinitely in UI.
- #20 (Med): LLM judge calls (llm_dedupe, contradictions) have no per-pair exception handling → one transient timeout aborts whole weekly pass.
- #21/#22 (Low): BM25 default weights (tag matches rank equal to content), style formality = tech-word ratio mislabeled.

### D. Workflows — COMPLETE
**CRITICAL CONFIRMED BY MY OWN INSPECTION**: executor.py:366-378 dispatches NODE_TYPES executors and RETURNS before the gate block at :412-432. nodes/tool_call.py:54 calls `app.tool_registry.call(tool_name, tool_inputs)` directly — NO CapabilityGate, no confirmation, no audit. investigate.py same pattern with tools from interpolated inputs. workflow.trust_level stored/API-validated/UI-shown but NEVER ENFORCED anywhere. Webhook-triggered workflows can run `terminal` etc. unattended. Directly contradicts gate.py's own docstring claim and ADR-042.
Also confirmed by me: sync artifact_store.fetch_content in async paths (executor.py:438, tool_call.py:56) blocks event loop; workflow_completed published with source_workflow_id at :338-347.

Other findings (agent):
- **#2 (High)**: workflow_completed self-trigger infinite loop — match-all when source_workflow_id None (triggers.py:266-268); no depth limit.
- **#3 (High)**: no cancellation, no max-duration guard, no concurrency control; stalled LLM node hangs execution forever; fire-and-forget bus task leak.
- **#4 (High)**: cron schedule triggers only evaluate inside OTHER tasks' schedule_fired events → with no other scheduled tasks, cron workflows NEVER fire; cron-less schedule workflows fire on EVERY system-wide event.
- **#5 (High)**: test runs execute production side effects (send_message really sends; ungated tools really run) and pollute production execution history; no dry-run/is_test flag.
- **#6 (High)**: crash mid-execution leaves zero record (save only at end/fail-fast; no RUNNING state).
- **#7 (Med)**: chat-command trigger match-all fires on every slash-command from any user incl. payload text injection into prompts.
- **#8 (Med)**: send_message destination resolvable from attacker-influenced inputs (_resolve prefers inputs over config).
- **#9 (Med)**: owner_id mass assignment + trust_level self-service on API create/update.
- **#10/#11 (Med)**: invalid LLM decision returned not failed → status ok with half graph vanished silently; skipped nodes invisible (no NodeResult).
- **#12 (Med)**: unbounded HTTP responses into memory/persistence; no egress audit on workflow HTTP node.
- **#13 (Med)**: webhook replay cache process-local, evictable (>1000 hits/5min), wiped on restart.
- **#14 (Med)**: /api/workflows/dashboard cross-owner data incl. raw trigger payloads for any authenticated user (= web-layer F4, dedup).
- **#15 (Med)**: interpolation fails silent (missing key → ""); dict/list str() renders Python repr corrupting JSON templates.
- #16-#22 (Low): no save-time validation, trigger_type free-form, node-config secrets unredacted in versions API, URL-extraction heuristic mangles output, condition ops eager-eval (NameError on short-circuit expectations), find_pending cross-workflow misrouting, sync artifact reads block loop.

Good: SSRFSafeTransport reused on HTTP node (validates redirect hops), webhook HMAC textbook (compare_digest, ±300s, reveal-once secrets, sentinel round-trip), Kahn cycle check, AST-whitelisted condition eval (safe mini-language).

### E. Tools/Policy/Security — COMPLETE
GATE ENFORCEMENT MAP (primary deliverable): Gate invoked from exactly 2 places: orchestrator _run_capability_gate (execution.py:1538 via _check_confirmation:1458 from _dispatch_tool_call:1677 + _meta_call_tool:1628) and workflow executor FALLBACK only (:425). Four bypasses confirmed:
1. **Policy-delegation path** calls delegate_task directly (execution.py:1410) — destructive-classified tool ungated, unaudited.
2. **Workflow tool_call node** (tool_call.py:54) — VERIFIED BY ME.
3. **Workflow investigate node** (investigate.py:70).
4. **Truncated-write recovery** (quality.py:200) invokes raw write_file handler — skips killswitch/injection escalation/audit; recovery writes even while context injection-flagged.

Other findings:
- F4 (Med): Channel.SUBAGENT in neither trusted nor unattended set → destructive calls approved; browser_login carries no capability label so filter_tools never strips it; developer preset auto_approve "*" → subagent can invoke browser_login.
- F5 (Med): orchestrator never passes allow_list to gate → TrustConfig.scheduler_shell_exec etc. silently dead (always denied not_allow_listed) while filter_tools advertises the tools → confusing denials + digest noise.
- F6 (Low): gate auto_approved verdict computed then discarded; PolicyEngine re-derives with divergent logic.
- F7 (Med): write_file/edit_file non-atomic (write_text direct truncate; no temp+replace); edit_file uncapped read; read_file loads ENTIRE file into RAM before slicing [:max_bytes] (OOM vector).
- F8 (Low): path sandbox solid (resolve()+relative_to handles symlinks/traversal); residual check-then-open TOCTOU; allowed_roots defaults empty (fail-closed good).
- F9 (Med): terminal output unbounded in RAM until completion (cat /dev/urandom | base64 = GB within window); timeout clamp absent; env fully inherited (printenv pulls secrets into context); killpg works properly (good).
- F10 (High): browser_get_json + browser_interact + check_health have NO assert_url_safe at all; even guarded fetch_url validates once pre-navigation — Chromium-side redirects/subresources/JS navigations unvalidated → metadata-endpoint exfil into model context.
- F11 (Med): DNS-rebinding TOCTOU acknowledged unpinned; curl_cffi weaker path; decimal/octal IP handled correctly though.
- F12 (Med): egress audit asymmetric: httpx records final URL only; curl_cffi records hops; Playwright records NOTHING.
- F13 (Med): use_curl_cffi is model-selectable → model can downgrade own SSRF boundary silently.
- F14 (Med): escalation wiring stringly-typed — `"[SECURITY NOTE:" in m.content`; any fetched page printing that literal flips subsequent destructive calls (content-driven DoS fail-closed); scanner FN surface trivial (4 regex families; structured >500 chars skips entropy check entirely).
- F15 (Med): artifacts manual-only GC (admin CLI only); orphaned .bin leak on crash-between-writes; inline.json whole-rewrite per store (quadratic I/O).
- F16 (Low-Med): subagent isolation reasonable (throwaway sessions, archived in finally, recursion blocked); timeout leaves half-written files no rollback.
- F17/F18 (Low): voice path channel=CLI misclassification (dup of RACE-02); cookies world-readable chmod; --no-sandbox chromium.

Good: gate-first ordering before confirmation/auto-approve, fail-closed preset fallback, stable confirmation tokens, meta-tool unwrapping prevents call_tool dodge, audit-on-deny with secret scrubbing, SSRF fundamentals correct where applied, terminal process-group kill correct, webhook ingestion textbook.

### F. Web layer/auth — COMPLETE (F1-F17)
- **F1 (High, Confirmed)**: `/api/auth/request-code` accepts client-supplied `platform_user` — code delivered to ATTACKER-CHOSEN recipient; allowlist check skipped when param present (auth.py:44-45,198-199,213).
- **F2 (Med)**: debug_login mints sessions for arbitrary user_id but startup security-posture guard checks only auth_enabled + auto_approve_tools, not debug_login.
- **F3 (Med)**: topic rename/delete/read IDOR (zero ownership checks vs sibling routes).
- **F4 (Med)**: /api/workflows/dashboard cross-user leak incl. node_results/errors (= workflows #14).
- **F5 (Med)**: owner_id mass assignment + trust_level self-service (= workflows #9, dedup).
- **F6 (Med)**: rate limiting ONLY on auth endpoints; heavy background jobs (doctor/audit) triggerable repeatedly by any user.
- **F7 (Med-Low)**: config route exposes metadata/identifiers to non-admins (core creds masked recursively - good).
- **F8 (Low)**: browser stream client sockets unclosed after server-side stop.
- **F9 (Low)**: screencast frame tasks fire-and-forget GCable mid-execution dropping frames/skips acks.
- **F10 (Med)**: headed-login flow no SSRF check (admin-gated; can point real Chromium at internal services).
- **F11 (Low)**: WS token enforced even when auth disabled (functional inconsistency); token in query string (log leakage); no Origin check (token mitigates).
- **F12 (Low)**: ADR-035 cache lazy TTL no eviction; caller-controlled max_age unbounded (pin stale results forever).
- **F13 (Low)**: unbounded list endpoints (egress full-table dump, scheduler tasks, memory limit uncapped, topics/users unbounded).
- **F14 (Low)**: scheduler routes have INVERSE privilege bug — admins locked out of managing others' tasks.
- **F15 (Info)**: non-constant-time dict lookups for codes/tokens (mitigated by entropy/rate limits).
- **F16 (Info)**: verbose error detail discloses platform config state to anonymous callers.
- **F17 (Med, Confirmed)**: /api/auth/available-users UNAUTHENTICATED roster disclosure — user_ids, display names, roles, platforms, identity bindings; synergistic with F1 targeting.

Good: webhook auth exemplary, layered authorization honest fallbacks, token hygiene (memory-only sessions, token_urlsafe(32)), startup security posture hard-fail with documented escape hatch, StaticFiles traversal-safe, no CORS needed (sessionStorage bearer), proxy header handling safe.

### G. Frontend web-ui — MOSTLY COMPLETE
Build: **BROKEN on current branch** — `useWorkflowEditor.ts:160` references `wf.secret` not on Workflow type → TS2339, npm run build FAILS. Vite build OK separately: single JS chunk 2,739.79 kB (800 kB gzip!) — React Flow loaded on Login/Dashboard; @openuidev/react-ui used only for ThemeProvider/createTheme (pure overhead). Inline styles: 12 (< 20 PASS). Contrast: muted 3.54:1 / dark-muted 3.87:1 / warning-text 2.94:1 — AA FAILS.

Bugs: B1 broken build; B2 polling emits unhandled promise rejections; B3 dead AbortController + setState-after-unmount in loadExecutions; B4 Proposals/Dashboard/Config tab-switch race (stale response lands last); B5 BrowserStream draws at stale canvas size after resize; B6 stale closure logout deps; B7 `showTrash || true` dead toggle; **B8 (high) Save & Activate transient failure renders full-page ErrorState replacing canvas → unsaved graph destroyed, retry=window.location.reload()**; B9 CronBuilder Custom switch wipes schedule silently (empty validates clean); B14 silent JSON discard in JsonTextarea; B16 memory-edit errors behind modal overlay. (B10-B13, B15, B17 pending recovery.)

A11y: A1 modals lack Escape/focus-trap/restore/aria-labelledby (Tab reaches background); A2 contrast tokens fail AA (above); A3 clickable tr/div not keyboard operable; A4 login code input unlabeled; A5 no prefers-reduced-motion; A6 color-only status dots.

UX: U1 inconsistent destructive confirms (native confirm vs styled dialog); U2 webhook secret shown PLAINTEXT on screen beside Copy; U3 inconsistent date formatting (toLocaleString vs helpers vs raw ISO vs reimplemented relative time); **U4 (high) workflow editor friction: raw node-type IDs in toolbar select, generated node_xxx IDs in variable pickers, {{data.X}} wrapping applied wrongly to upstream refs, viewing old version marks editor dirty, no version diff**; U5 dead API surface (saveConfig unused/config read-only, deferProposal never imported despite backend support — no Defer button!, fetchMemories unused); **U6 (high) session expiry loses work: transient fetchAuthStatus failure kicks authenticated users to Login; ANY 401 clears token instantly discarding unsaved editor work**; U7 hardcoded values wanting config (Approve/Deny literals, Telegram 4096 limit enforced for all platforms, STATIC_PLATFORMS fallback); U8 papercuts (global Check Now disable, form reset inconsistencies, "Filter" label misuse, half-reset style state, full-page-reload nav in Knowledge).

Perf: P1 single 2.74MB chunk zero splitting (high certain); P2 openui pure overhead drop candidate; P3 poll flicker churn table remount every 5s; P4 WS mousemove flood no throttle; P5 minor rerender hotspots; P6 no virtualization acceptable now.

Good: centralized copy catalog text.ts tested; race-safe useApiQuery requestId+mountedRef; correct undo/redo semantics; disciplined CSS tokens w/ dark parity + smoke test enforcing inline budget; 30s timeout fetch + 401 custom-event decoupling; 11 page suites + 23 Playwright specs.

### H. Tests — COMPLETE
RUN RESULTS: `pytest tests/unit tests/integration`: **2272 passed / 6 skipped / ~260s**, deterministic ×4 runs. mypy: **7 errors** (voice/pipeline.py optional-dep guards, stealth.py import-untyped). ruff: **49 errors** (27 auto-fixable) — QUALITY GATES RED on runtime branch.
Invariant coverage: SSRF deepest-in-repo YES; injection escalation YES (gate+orchestrator+scanner); migration idempotency PARTIAL (platform migrations yes; Alembic zero coverage); confirmation requester binding YES; concurrency races REAL (20-writer gather tests with exact post-state); bonus slot-manager concurrency, IMAP serialization.
Missing coverage: rollback_turn tool, scheduler_tools ownership verification (_verify_task_ownership), Alembic replay harness, web routes partially, voice/email/browser thin.
Quality strengths: mocking altitude correct (fakes at true boundaries: inference client, IMAP socket, respx HTTP, Playwright), decision traceability (docstrings cite audit IDs/ADRs), docs-as-tests, fast deterministic.
Weaknesses: red gates (ruff 49 / mypy 7) indicate gates not enforced recently; fixture duplication between trees; no pytest-timeout config; handoff-flow teardown warning.

## Phase 3: Orchestrator/inference deep-dive — COMPLETE

22 findings registered by agent + my direct verification of Critical items:
- **BUG: Session-lock pop race (Critical, verified by me)**: lock.py:40-51 pops dict entry whenever `locked()` is False; asyncio.Lock reports unlocked between release() and waiter resumption; engine.py:320 calls release_unused synchronously right after `async with` exits → pending waiter stranded on orphaned Lock object; next arrival creates fresh lock → two turns same session run concurrently. Also runners.py:182 same call. is_locked() probes lie (scheduler/engine.py:139, compaction.py:73).
- **Slot eviction I/O outside pool lock (High)**: slot_manager.py:289-302 releases pool lock then awaits slot_save/slot_erase; concurrent acquire claims slot mid-operation → snapshot cross-contamination/KV erase underneath new owner. finalization.py:127-131 erases by session.slot_id without ownership recheck.
- **Stream stall → fake "stop" finish_reason (High, Confirmed)**: execution.py:800-817 catches TimeoutError mid-stream, sets stop, proceeds DONE path — silent truncation; non-streaming equivalent raises → FAILED/retry asymmetry.
- Thinking budget enforced only when streaming (F4); transient-inference retry policy dead code (F5); dangling tool_calls brick session after crash-window (F7 potential); turn persistence drops outcome fields (F8); recover_stale_turns startup-only (F9); naive datetime in stale-turn query (F10); IllegalTransition bypasses journal (F11); rate-limit double notification (F12); quality greeting false-positive (F13); truncated-write recovery outside gate (F14 = SEC-003); stale request_token reuse (F15); total_reasoning_tokens never incremented (F16); pre-tool chatter streamed + 💭 prefix never streamed (F17); /reset cancels nothing (F18); mid-stream abort leaves SSE generator unclosed (F19); SSE error events swallowed → 120-180s stall masquerading as truncation (F20); confirmation holds session lock ≤60s per gated tool, AWAITING_USER state never emitted (F21); rollback_turn restores files only, checkpoints in-memory only (F22).
- Efficiency: full re-tokenization per loop iteration; no stream_options include_usage; envelope re-calibration per build; full context rebuild for correction/nudge iterations; consumed meta-tool payloads persist forever; breaker state rescanned O(history) per dispatch.
- Done well: explicit transition table + journal; five tailored degeneracy circuit breakers w/ regression fixture capture; server-truth /tokenize counting; confirmation hardening; typed error taxonomy.

### Verification notes (my own reads)
- app.py read fully: clean composition root, eager stores + lazy cached_properties; make_orchestrator creates a SECOND HandoffService instead of reusing self.handoff_service (app.py:244 vs 477-480); close() only closes inference+email (DB engine never closed); C1/C3 startup guards good but skip debug_login (web F2 confirmed); bootstrap check-then-await race confirmed (app.py:409-423).
- serve.py read fully: monkey-patches `app.inference.close = _noop_close` (line 34, brittle); one platform task crash propagates through gather killing ALL platforms (line 154-155, confirms COR-04); trigger registry never stopped on shutdown; email adapter not closed via app.close() in run_platform path.
- runners.py:395-433: shutdown path closes scheduler→adapter→inference only; recover_stale_turns invoked only here + chat command.
- config.py structure skimmed: typed dataclasses w/ env overrides, trust presets as classmethods, masked reprs — sound design.

## Phase 4: Runtime observations (live system)

- Service RUNNING: PID 825040 `hestia --config config.runtime.py serve`; llama-server on :8001 (Ornith-1.0-35B MTP model per forensic doc, `-c 393216 -np 3`).
- Web dashboard live on **0.0.0.0:8765** with auth_enabled=True, debug_login=False; /api/health returns ok; SPA index served (401B shell).
- Live DB (`runtime-data/hestia.db`, 20MB): messages 7430, turn_transitions 12825, turns 685, sessions 262, compaction_archive 1022, traces 631, egress_events 778, capability_events 1(!), failure_bundles 183, workflow_executions 119, workflows 4, users 5, memory 147.
- **Measured: journal_mode=delete, foreign_keys=0** → confirms persistence F2 (no WAL/busy_timeout/FK enforcement) on the LIVE database.
- **Measured: NO index exists on messages table** (schema.py defines table without any Index; index list from live DB confirms). Hottest table scanned fully per context build. Also sessions has no last_active_at index (only platform/state partial indexes).
- `session_handoffs`: 46 rows of legacy data despite zero code readers/writers (dead table with stale data).
- capability_events: only 1 row ever — audit trail nearly empty in practice (either gate rarely denies or events not persisted as designed; worth follow-up).
- runtime-data/logs/llama-crash-forensic-2026-08-13.md: two llama-server SIGABRT crashes during slot save/LCP-reuse operations on GPU1 (x4 link), cuBLAS STATUS_NOT_SUPPORTED; MTP draft decoding disabled afterward; stable since. Upstream fork bug, but proves slot-op interleaving crashes are real, raising stakes for BUG slot-race finding.
- artifacts dir: 67MB (manual-only GC consistent with artifact finding).

## Phase 5: Git history hotspots (since 2026-01-01, file touch counts)

config.py 93, orchestrator/engine.py 92, cli.py 89, app.py 88, execution.py 67, telegram_adapter.py 49, web-ui/api/client.ts 47, tools/builtin/__init__.py 39, context/builder.py 39, core/inference.py 38 — churn concentrated in config/engine/app = composition + policy surface, matching complexity findings.

## Phase 6: Frontend findings completion

B10 audit/doctor unhandled rejections; B11 bare clipboard writes; B12 NO React error boundary anywhere (white-screen risk); B13 5s poll blanks sessions table (isLoading toggles skeleton every tick); B15 Config Reveal is a no-op ('***' literal); B17 node/trigger form validation gaps. All A1-A6, U1-U8, P1-P6 recovered and logged above.

## Synthesis themes (final)

1. **Trust-boundary theater**: ADR-042's universal-gate claim contradicted by 4 bypass paths + dead controls (workflow trust_level, scheduler allow-list flags, gate auto_approved verdict). Root cause: ToolRegistry.call is the real chokepoint and performs zero checks; gating lives at ONE call site conventionally.
2. **Concurrency discipline gaps**: session-lock pop race, slot eviction race, sequential Telegram processing, head-of-line scheduler ticks, fire-and-forget tasks everywhere (bus handlers, frame tasks, pollers) without lifecycle/cancellation/backpressure.
3. **Silent-failure default**: interpolation "", skipped nodes invisible, silent cron misses, silent allowlist mismatch, fake-stop truncation, swallowed SSE errors, silent JSON discard in FE — system consistently chooses silence over actionable feedback.
4. **Duplication without shared helpers**: WHERE builders ×4 (two broken), edit rate-limits ×2, reset flows ×2 divergent, timestamp formats fragmented, FE date formats ×5 styles, destructive-confirm patterns ×2.
5. **Data hygiene**: 9 unbounded tables incl. maintenance_trace embedding content blobs; dead session_handoffs w/ legacy rows; Alembic drift; triple DDL sources.
6. **Frontend solid bones, red gates**: good copy catalog/query hook/undo-redo/CSS tokens; but build BROKEN on branch, 800KB gzip single chunk, AA contrast failures, no error boundary.

Finding ID scheme assigned in deliverables: SEC-001..SEC-023, BUG-001..BUG-05x (consolidated register ~45 entries), PERF-001..PERF-016, UX-001..UX-016, ARCH-001..ARCH-009, TEST-001..TEST-008, MAINT-001..MAINT-01x, DX-001..DX-00x. Cross-references preserved to agent finding numbers where useful.

## Cross-cutting synthesis candidates (early)

1. **Trust-boundary theater**: ADR-042 claims universal gate; reality = 4 bypasses + dead controls (trust_level, scheduler flags, auto_approved). Root cause: enforcement-by-convention rather than chokepoint; ToolRegistry.call is the real chokepoint and it does nothing.
2. **Fire-and-forget culture**: bus tasks, frame tasks, pollers, background loops — repeated patterns of unawaited tasks, missing cancellation, unbounded growth (matrix _last_edit_times, artifact bins, traces, maintenance_trace, stream states).
3. **Silent-failure UX**: interpolation "", swallowed errors, invisible skipped nodes, silent cron misses, silent allowlist mismatch — recurring theme across layers.
4. **Divergent duplicated logic**: reset flows, edit rate limits, WHERE-clause builders ×4, timestamp formats, date formatting in FE, confirms in FE — shared-helper absence causes bugs that recur per-copy.
