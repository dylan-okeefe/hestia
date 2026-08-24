# Bug & Reliability Register — Hestia

**Audit date:** 2026-08-22 · Confidence legend: **Confirmed** = code path traced (and where noted, verified by direct inspection or measured at runtime); **Highly likely** = strong evidence, reproduction impractical in audit window; **Potential risk** = plausible, needs targeted investigation.
Severity assumes the deployment posture Hestia is written for: single process, one principal user + household, local llama-server, web dashboard possibly LAN/Tailscale-exposed.

Security-classified findings (SEC-\*) are registered here in summary and detailed in `08_SECURITY_PRIVACY.md`. Performance-only items live in `06_PERFORMANCE.md`.

---

## Master table

| ID | Title | Subsystem | Severity | Confidence |
|----|-------|-----------|----------|------------|
| BUG-001 | Session-lock pop race breaks per-session serialization | orchestrator | Critical | Confirmed |
| SEC-001 | Workflow tool_call/investigate nodes bypass CapabilityGate | workflows/policy | Critical | Confirmed |
| BUG-002 | Slot eviction I/O outside pool lock races allocate/restore | inference | High | Highly likely |
| BUG-003 | Stream stall converted to fake "stop"; silent truncation | orchestrator/inference | High | Confirmed |
| BUG-004 | workflow_completed self-trigger infinite loop | workflows | High | Confirmed (logic) |
| BUG-005 | Cron schedule triggers only fire when unrelated tasks fire | workflows/scheduler | High | Confirmed |
| BUG-006 | Telegram sequential updates block every chat behind one slow turn | platforms | High | Highly likely |
| BUG-007 | Trace/failure store IN-clause binding crash | persistence | High | Confirmed |
| BUG-008 | SQLite untuned: FKs off, no WAL/busy_timeout; lock errors unhandled | persistence | High | Confirmed (measured) |
| BUG-009 | PostgreSQL path broken (m006 pragma; asyncpg timestamp strings) | persistence | High (PG) | Highly likely |
| BUG-010 | Memory merge/supersede ignore update() failure before deleting losers | memory | High | Confirmed |
| BUG-011 | FTS5 syntax errors uncaught; maintenance passes crash on content-derived queries | memory | High | Confirmed |
| BUG-012 | Failed tasks retry every 30 s forever; "capped backoff" dead code | scheduler | High | Confirmed |
| BUG-027 | Multi-tool turns lose sibling tool results from context | context | High | Confirmed |
| BUG-037 | Workflows: no cancellation, duration ceiling, or concurrency control | workflows | High | Confirmed |
| BUG-041 | Workflow test runs execute production side effects & pollute history | workflows/web | High | Confirmed |
| BUG-049 | Frontend build broken (`wf.secret` TS2339) | web-ui | High | Confirmed (measured) |
| BUG-055 | Any 401 / transient auth-status failure logs user out instantly, discarding work | web-ui | High | Confirmed |
| BUG-056 | Save & Activate transient failure destroys unsaved graph (reload as retry) | web-ui | High | Confirmed |
| SEC-002 | Login-code dispatch to attacker-chosen recipient; unauth roster disclosure | web auth | High/Med | Confirmed |
| SEC-005 | Browser tools missing SSRF checks; redirects/subresources unvalidated | tools/browser | High | Confirmed |
| SEC-010 | Memory list/delete/update fail open without identity → cross-user access | memory | High | Confirmed |
| BUG-013 | Matrix boot-sync failure kills entire serve process | platforms | Medium | Confirmed pattern |
| BUG-014 | Voice turns auto-deny confirmations; channel misattributed CLI | platforms | Medium | Confirmed |
| BUG-015 | Confirmation prompts break on markdown metacharacters (no fallback) | platforms | Medium | Confirmed |
| BUG-016 | Multi-chunk edit fallback duplicates or drops chunks | platforms | Medium | Confirmed |
| BUG-017 | Email poison-message infinite redelivery | email | Medium | Confirmed |
| BUG-018 | Email N+1 INTERNALDATE fetches; UID-as-epoch fallback bug | email | Medium | Confirmed |
| BUG-019 | Crash window leaves dangling tool_calls → session 400s until surgery | orchestrator/context | Medium | Potential risk |
| BUG-020 | Thinking budget enforced only when streaming | orchestrator | Medium | Confirmed |
| BUG-021 | Transient-inference retry policy dead code; backoff ignored | orchestrator | Medium | Confirmed |
| BUG-022 | SSE server error events swallowed → 120–180 s stall masquerades as truncation | inference | Medium | Highly likely |
| BUG-023 | `/reset` cancels nothing; in-flight turn keeps writing to archived session | platforms/orchestrator | Medium | Highly likely |
| BUG-024 | Quality heuristics false-positive (greetings mid-task; benign "error" text) | orchestrator/quality | Medium | Confirmed |
| BUG-025 | rollback_turn restores files only; checkpoints die with process | tools/checkpoint | Medium | Confirmed |
| BUG-026 | One LLM-judge error aborts whole weekly dedupe/contradiction pass | memory/maintenance | Medium | Confirmed |
| BUG-028 | Compression splice bypasses sequence validation; can orphan tool message | context | Medium | Highly likely |
| BUG-029 | EventBus.publish_nowait fallback destroys its own handler tasks | events | Medium (latent) | Confirmed |
| BUG-030 | Scheduler tick head-of-line blocking; at-most-once cron across crashes | scheduler | Medium | Confirmed |
| BUG-031 | Epoch composition loads entire memory table per session start | memory/context | Medium | Confirmed |
| BUG-036 | Crash mid-workflow leaves zero record (persist only at terminal) | workflows | Medium | Confirmed |
| BUG-038 | Invalid LLM decision returns ok with half graph silently vanished | workflows | Medium | Confirmed |
| BUG-039 | Skipped nodes emit no NodeResult — invisible to UI/debugging | workflows | Medium | Confirmed |
| BUG-040 | HTTP node: uncapped response into memory/DB/API; no egress audit | workflows | Medium | Confirmed |
| BUG-043 | Workflow response interception hijacks unrelated messages; buttons unauthenticated | platforms/workflows | Med-High | Confirmed |
| BUG-050 | Polling emits unhandled promise rejections | web-ui | Medium | Confirmed |
| BUG-051 | 5 s poll blanks sessions table via isLoading skeleton toggle | web-ui | Medium | Confirmed |
| BUG-052 | Tab-switch races let stale responses land last (Proposals/Dashboard/Config) | web-ui | Medium | Confirmed |
| BUG-057 | CronBuilder Custom switch silently wipes schedule | web-ui | Medium | Confirmed |
| BUG-058 | No React error boundary anywhere — render exception white-screens app | web-ui | Medium | Confirmed |
| BUG-067 | Timestamp format fragmentation → wrong same-day comparisons in schedulers | persistence/style/reflection | Medium | Confirmed (logic) |
| BUG-069 | Interpolation fails silent (""); containers render as Python repr corrupting JSON templates | workflows | Medium | Confirmed |
| BUG-078 | Confirmation escalation holds session lock ≤60 s/tool; AWAITING_USER never emitted | orchestrator | Low-Med | Confirmed |
| BUG-032 | Matrix prefix command matching (`/resetnow` resets) | platforms | Med-Low | Confirmed |
| BUG-033 | send_draft deletes draft even if Sent COPY failed | email | Med-Low | Confirmed |
| BUG-044 | Auth-code filter drops any all-digit 4–10 char user message globally | context | Low-Med | Confirmed |
| BUG-062 | Voice temp-file leak on download failure | platforms | Low | Confirmed |
| BUG-063 | Voice typing indicator targets wrong chat in groups | platforms | Low | Confirmed |
| BUG-064 | `@username` allowlist entries never match (normalization mismatch) | platforms | Low-Med | Confirmed |
| BUG-065 | Matrix lacks message chunking; >~64 KB responses fail outright | platforms | Med-Low | Confirmed |
| BUG-066 | Matrix edit rate-limit map never evicts (unbounded growth) | platforms | Low | Confirmed |
| BUG-035 | recover_stale_turns startup-only; hung turns stay non-terminal until restart | orchestrator | Medium | Confirmed |
| BUG-049b=BUG-083 | Config "Reveal" is a no-op over literal `'***'` | web-ui | Low | Confirmed |
| BUG-084 | Knowledge trash toggle dead (`showTrash \|\| true`) | web-ui | Low | Confirmed |
| BUG-053 | Editor AbortController never wired; setState-after-unmount possible | web-ui | Low-Med | Confirmed |
| BUG-054 | Audit/doctor actions lack catch — failures invisible | web-ui | Low | Confirmed |
| BUG-085 | BrowserStream draws frames at stale canvas size after resize | web-ui | Low-Med | Confirmed |
| BUG-086 | Logout callback stale closure over `debugLogin` | web-ui | Low | Confirmed |
| BUG-087 | Node form `Number('')===0` defeats min-validation; trigger forms save incomplete configs | web-ui | Low | Confirmed |
| BUG-070 | Condition node boolean ops evaluate eagerly (NameError vs short-circuit) | workflows | Low | Confirmed |
| BUG-071 | No save-time graph validation; trigger_type free-form on update | workflows/api | Low-Med | Confirmed |
| BUG-038b=BUG-088 | get_turn_messages duplicated ×2, zero callers, wrong join semantics | persistence | Low | Confirmed |
| BUG-068 | Bootstrap flag check-then-await race (benign duplication today) | app | Low | Confirmed |
| BUG-045 | Pre-tool chatter streamed; final 💭 reasoning prefix never streamed (content swap) | orchestrator/platforms | Low | Confirmed |
| BUG-046 | Mid-stream abort leaves SSE generator unclosed | orchestrator/inference | Low | Confirmed |
| BUG-079 | `total_reasoning_tokens` declared/read but never written — traces always null | orchestrator/traces | Low | Confirmed |
| BUG-080 | IllegalTransition handler bypasses transition journal | orchestrator | Low | Confirmed |
| BUG-081 | Naive-vs-aware datetime cutoff in stale-turn query | persistence | Low | Potential risk |
| BUG-082 | Scheduler routes have inverse privilege bug (admins locked out of others' tasks) | web routes | Low (functional) | Confirmed |
| BUG-072 | Dropped-history slice includes protected first message (over-reports truncation; duplicate tokens post-splice) | context | Low | Highly likely |
| BUG-073 | LIKE fallback doesn't escape `%`/`_` wildcards | memory | Low | Confirmed |
| BUG-074 | Tag filter quotes without escaping embedded quotes → MATCH errors | memory | Low | Confirmed |
| BUG-075 | maintenance_trace grows unboundedly embedding merged-content blobs | memory | Low-Med | Confirmed |
| BUG-076 | BM25 default weights: tag matches rank equal to content matches | memory | Low | Confirmed |
| BUG-077 | Style "formality" is tech-word ratio incl. everyday words — mislabeled tone | style | Low | Confirmed |
| SEC-003..SEC-023 | See security doc | various | various | various |

---

## Detailed entries — Critical & High

### BUG-001 — Session-lock pop race breaks per-session serialization
- **Subsystem:** orchestrator/concurrency · **Severity:** Critical · **Confidence:** Confirmed (verified by direct inspection)
- **Files:** `src/hestia/orchestrator/lock.py:40-51`, `engine.py:233-234,320`; `platforms/runners.py:180-182`; probes at `scheduler/engine.py:139`, `orchestrator/compaction.py:73`
- **Mechanism:** `release_unused` pops the dict entry whenever `lock.locked()` is False. An asyncio.Lock reports unlocked between `release()` and waiter resumption. `process_turn` calls `release_unused(session.id)` synchronously immediately after the `async with lock:` exits.
- **Interleaving:** A releases → waiter B pending on orphaned object → entry popped → C arrives, gets fresh lock, runs concurrently with B.
- **Expected:** one turn per session at a time (ADR-041). **Actual:** two concurrent turns possible, silently, no log.
- **Impact:** voids invariant that message ordering, slot save/erase pairing, stream-state handoff depend on; makes `is_locked()` probes lie.
- **Repro:** two rapid messages to one session while first is mid-turn; requires waiter present at release instant (common under load).
- **Fix direction:** never prune while waiters exist (track waiter count), or refcount-based lifecycle. **Scope:** S (~20 lines + tests).

### SEC-001 — Workflow tool_call/investigate nodes bypass CapabilityGate
- **Subsystem:** workflows/policy · **Severity:** Critical · **Confidence:** Confirmed (**verified by direct inspection**, independently found by two audit passes)
- **Files:** `workflows/executor.py:366-378` (NODE_TYPES dispatch returns before gate at :412-432), `nodes/tool_call.py:54`, `nodes/investigate.py:68-70`
- **Actual:** any activated workflow — including webhook-triggered — invokes arbitrary tools (`terminal`, `write_file`, email send) with zero gate evaluation, confirmation, killswitch, injection escalation, or audit. `workflow.trust_level` and `allow_listed_tools` are dead controls on these paths.
- **Expected:** ADR-042 "single trust/capability boundary for every tool execution path."
- **Fix direction:** route both nodes through `capability_gate.check` (owner identity, Channel.WORKFLOW, allow_list); better, move enforcement into/wrapping `ToolRegistry.call` so the ungated path cannot be reconstructed (see ARCH-001). Regression test: paranoid workflow invoking `terminal` must be denied. **Scope:** M.

### BUG-002 — Slot eviction I/O outside pool lock
- **Severity:** High · **Confidence:** Highly likely · **Files:** `inference/slot_manager.py:289-302`; `orchestrator/finalization.py:127-131`
- **Actual:** eviction releases pool lock then awaits slot_save/slot_erase; concurrent acquire claims slot mid-operation → snapshot cross-contamination; KV erase under a new owner. Finalization erases by stored `session.slot_id` without ownership recheck.
- **Context:** operator's llama-crash forensics show real crashes during slot-op interleavings (upstream cuBLAS bug triggered by exactly this class of overlap).
- **Fix direction:** hold pool lock across save/erase (or per-slot state machine with ownership tokens). **Scope:** M.

### BUG-003 — Stream stall → fake "stop", silent truncation
- **Severity:** High · **Confidence:** Confirmed · **Files:** `execution.py:800-817`
- **Actual:** TimeoutError inside streaming loop sets `finish_reason="stop"`, proceeds DONE path; user receives truncated answer presented as complete. Non-streaming equivalent raises → FAILED/retry. Same condition, opposite outcomes.
- **Fix:** raise InferenceTimeoutError (unify), or append visible "[response interrupted]" marker + FAILED classification. **Scope:** S.

### BUG-004 — workflow_completed self-trigger infinite loop
- **Severity:** High · **Confidence:** Confirmed (logic) · **Files:** `executor.py:338-347`, `triggers.py:266-268`, `_on_event:105-121`
- **Actual:** completed-trigger workflow with unset source_workflow_id matches its own completion event → re-executes forever, spawning bus tasks, consuming tokens, inserting rows. No depth limit/dedup anywhere.
- **Fix:** refuse self-delivery; depth-limit chains; validate activation-time config. **Scope:** S.

### BUG-005 — Cron schedule triggers piggyback on unrelated scheduler fires
- **Severity:** High · **Confidence:** Confirmed · **Files:** sole publisher `scheduler/engine.py:172-181`; matcher `triggers.py:194-212`; match-all hole at :196-198
- **Actual:** cron workflows evaluate only when some other scheduled task fires within the same minute; with no other tasks they never fire. Cron-less schedule workflows fire on every event system-wide.
- **Fix:** register schedule-triggers as first-class SchedulerStore tasks (pattern exists: `maintenance/scheduler.py:33-90`); require valid cron at save. **Scope:** M.

### BUG-006 — Telegram head-of-line blocking
- **Severity:** High · **Confidence:** Highly likely (library default; no `concurrent_updates` in repo) · **Files:** `telegram_adapter.py:260` handler registration; handlers await full turns (`runners.py:298-308`)
- **Actual:** one slow turn (LLM/tools/60s confirmations/voice ffmpeg+STT) blocks all chats/users incl. `/start` and callback queries.
- **Fix:** enable PTB `concurrent_updates`; correctness rests on BUG-001 fix. **Scope:** S (+BUG-001 prerequisite).

### BUG-007 — IN-clause binding crash in trace/failure stores
- **Severity:** High · **Confidence:** Confirmed · **Files:** `trace_store.py:116-137`, `failure_store.py:116-137`
- **Actual:** session-id lists interpolated into `sa.text()` without expanding bindparams → SQLAlchemy tuple-binding error whenever filtering by sessions. Two of four duplicated WHERE-builders carry the bug.
- **Fix:** expanding bindparams (pattern exists in `error_resolution_store.py:69`); consolidate builders. **Scope:** S.

### BUG-008 — SQLite untuned (measured)
- **Severity:** High · **Confidence:** Confirmed · **Files:** `persistence/db.py` connect path; live DB pragmas
- **Measured:** `journal_mode=delete`, `foreign_keys=0`, no busy_timeout. Concurrent writes raise "database is locked" unhandled; readers block writers; orphan rows possible.
- **Fix:** WAL + `busy_timeout=5000` + `PRAGMA foreign_keys=ON` (with FK-violation audit before enabling). **Scope:** S–M.

### BUG-009 — PostgreSQL path broken
- **Severity:** High (PG deployments) · **Confidence:** Highly likely · **Files:** `migrations/__init__.py:194-202` (m006 `pragma_table_info` unguarded); raw-SQL isoformat strings vs asyncpg typed params in trace/failure/capability/user stores
- **Fix:** dialect-aware preflight everywhere; parameterized timestamps. **Scope:** M.

### BUG-010 — Merge/supersede ignores update() failure before deleting losers
- **Severity:** High · **Confidence:** Confirmed · **Files:** `dedupe.py:213-243`, `llm_dedupe.py:170-176`, `contradictions.py:168-173`; `store.update` False-return at `store.py:938-944`
- **Actual:** sanitizer can reject merged content (e.g., ≥2 `user:` markers across concatenated lines) → update() False discarded → winners keep stale content while losers soft-deleted pointing at them: information loss recorded as successful merge.
- **Fix:** abort merge on update failure; record skipped-action trace. **Scope:** S.

### BUG-011 — FTS5 syntax errors uncaught
- **Severity:** High · **Confidence:** Confirmed · **Files:** sanitizer `store.py:36-47` (operator-containing queries skip escaping; leading/trailing forms fall through); `search()` no try/except `:682-685`; unprotected callers `dedupe.py:260-265`, `llm_dedupe.py:227-232`, `contradictions.py:225-230`
- **Actual:** OperationalError propagates: interactive turns shielded by tool-level catch, nightly maintenance passes crash on memory-content-derived queries.
- **Fix:** escape in operator mode too; catch OperationalError → []; sanitize tag path (BUG-074). **Scope:** S.

### BUG-012 — Constant 30 s retry forever
- **Severity:** High · **Confidence:** Confirmed · **Files:** `scheduler.py:37-42` (`min(30,300)`), `engine.py:250-253`
- **Actual:** deterministically failing task hammers every 30 s indefinitely, logging full exceptions; max-backoff constant dead; comment promises capped backoff.
- **Fix:** exponential growth clamped to max + max-attempts/disable-with-notification. **Scope:** S.

### BUG-027 — Multi-tool turns lose sibling tool results
- **Severity:** High · **Confidence:** Confirmed · **Files:** `history_window_selector.py:76-79`
- **Actual:** pairing advances `i += len(pair_msgs)` instead of `i = j + 1`: shared assistant double-counted against budget; sibling tool result appears in neither included nor dropped accounting — lost from context and invisible to compressor.
- **Fix:** advance to `j+1`; add 2-tool-call unit test. **Scope:** S.

### BUG-037 — Workflows: no cancellation / ceiling / concurrency control
- **Severity:** High · **Confidence:** Confirmed · **Files:** `executor.py:257-309`; spawn-per-event `app.py:453-456`; bus fan-out `bus.py:49-55`
- **Actual:** stalled LLM node hangs execution forever (fire-and-forget task leak); interpolated `timeout_seconds: 100000` honored; simultaneous triggers run fully parallel with interleaved side effects.
- **Fix:** asyncio.wait_for ceiling (configurable), per-workflow mutex/coalescing, cancel endpoint setting between-node flag + cancelling in-flight task. **Scope:** M.

### BUG-041 — Test runs execute production side effects
- **Severity:** High · **Confidence:** Confirmed · **Files:** `routes/workflows.py:477-482`; same executor/store/history
- **Actual:** Send-message nodes really send; ungated tools really run (SEC-001 compounds); results pollute production executions shown as last-execution status.
- **Fix:** is_test flag/in-memory sink; exclude from status aggregates; optional dry-run preview. **Scope:** M.

### BUG-049 — Frontend build broken
- **Severity:** High · **Confidence:** Confirmed (measured) · **Files:** `useWorkflowEditor.ts:160` vs `api/client.ts:240-251`
- **Actual:** `npm run build` fails TS2339 (`secret` not on Workflow type) — gates evidently not run on last change.
- **Fix:** type the field or use the dedicated secret endpoint; restore green build; re-wire web-ui build into gates. **Scope:** XS.

### BUG-055 — Instant logout on any 401 / transient auth-status failure
- **Severity:** High · **Confidence:** Confirmed · **Files:** `client.ts:54-57`, `AuthContext.tsx:80-90`
- **Actual:** single 401 clears token immediately (unsaved editor work gone); transient network failure during fetchAuthStatus also flips authenticated→false.
- **Fix:** grace/retry for auth-status failures; 401 handling distinguishes expiry (re-auth banner preserving drafts) from hard invalidation. **Scope:** S–M.

### BUG-056 — Save & Activate destroys unsaved graph on transient failure
- **Severity:** High · **Confidence:** Confirmed · **Files:** `useWorkflowEditor.ts:329` → `WorkflowEditor.tsx:161-169`
- **Actual:** page-level error renders full-page ErrorState replacing canvas; retry = `window.location.reload()`. Plain-save path correctly uses toast.
- **Fix:** toast + keep editor mounted for activate failures. **Scope:** XS.

*(SEC-002, SEC-005, SEC-010: full detail in `08_SECURITY_PRIVACY.md`.)*

## Detailed entries — Medium (condensed)

| ID | Evidence (files) | Actual vs expected | Fix direction | Scope |
|---|---|---|---|---|
| BUG-013 | `matrix_adapter.py:129`; `serve.py:154-155` | boot-sync exception kills all platforms vs degrade one adapter | try/backoff initial sync; gather isolation per platform | S |
| BUG-014 | `telegram_adapter.py:1061-1070`; ContextVars set only in `runners.py:195-199`; channel fallback `execution.py:1512` | voice turns: confirmations auto-denied; channel=CLI; runner-side checks skipped | route voice through runner or bind vars/channel explicitly | S |
| BUG-015 | `telegram_adapter.py:604-632` | markdown parse failure aborts confirmation vs plain-text fallback (exists at :321-330) | reuse escaping/plain fallback | XS |
| BUG-016 | `telegram_adapter.py:391-439` | "not modified" marks success skipping chunks[1:]; later-chunk failure resends all chunks | track delivered chunk index; resend only remainder | S |
| BUG-017 | `email_inbound.py:76-90` | failing UID retried every 30 s forever vs DLQ/backoff | mark-read-before-publish or attempt counter + park | S |
| BUG-018 | `email/adapter.py:319-332` | O(N) FETCH round-trips; UID treated as epoch in fallback sort | batch FETCH (flags+internaldate); drop epoch fallback | S |
| BUG-019 | persist assistant w/ tool_calls `execution.py:402-404` before results `:718-721`; builder no repair `builder.py:385-402` | crash window bricks session (strict template 400s) until manual DB edit | synthesize "[turn interrupted]" filler results on load | S |
| BUG-020 | raise site streaming-only `execution.py:821-834`; non-streaming `:334-340` | runaway reasoning unchecked with stream=false; nudge machinery dead | enforce budget in both paths | S |
| BUG-021 | policy maps retries `default.py:144-164`; except catches only budget error `execution.py:341`; backoff ignored | transient llama blips → immediate FAILED | honor retry_after_error for transient classes + sleep backoff | S |
| BUG-022 | parser skips non-data lines/errors `inference.py:656-674` | server rejections stall till 120–180 s timeouts then masquerade as truncation | detect `chunk.get("error")` → raise typed error | XS |
| BUG-023 | reset flow `telegram_adapter.py:673-718` archives session; in-flight turn continues appending/saving slot; stream states keyed by chat_id `:541` looked up later `runners.py:271-273` | /reset during active turn → writes to archived session; older stream may edit newer message | cancel/await in-flight turn on reset; generation-counter for streams | M |
| BUG-024 | `_is_greeting_mid_task` starts-with match `quality.py:481-486`; substring error scan `:419-434` | legit replies classified lost-context/PATCH_FAILED | tighten anchors; require tool-failure corroboration | S |
| BUG-025 | `rollback.py:44-51`; checkpoints in-memory `checkpoint.py:45`; git stash pop `:154-168` w/ swallowed failures | rollback partial (files only); useless post-crash; conflict-prone stash | scope honestly (docs+UI), persist checkpoints optionally, apply-with-keep | M |
| BUG-026 | bare judge awaits `llm_dedupe.py:267-271`, `contradictions.py:263-267` | one transient timeout aborts weekly pass; restart-from-scratch next week | per-pair try/catch + counted failures | XS |
| BUG-028 | validation before splice `builder.py:465-477`; splice returns unrevalidated `compressed_summary_strategy.py:62-82`; `pop(0)` pair-orphaning | strict-template 400s post-compaction | re-validate after splice; pop pairs | S |
| BUG-029 | `events/bus.py:66-68` | sync-publish fallback destroys pending handler tasks (currently unused path) | remove fallback or raise | XS |
| BUG-030 | tick lock held across turns `engine.py:132,150-151`; next_run pre-dispatch | HOL delays due tasks; crash skips occurrence | bounded-concurrency dispatch; claim row txn | M |
| BUG-031 | no LIMIT `store.py:585-613`; Python cap `epochs.py:88-118`; runs on /chat,/new,/ask,/refresh `memory_epochs.py:33-35` | full-table materialization per session start | LIMIT ~200 both buckets | XS |
| BUG-035 | recovery invoked only at startup `runners.py:398-401`, `commands/chat.py:39,114`; checkpoints in-memory | hung turns non-terminal until restart; no notification/runtime sweep | periodic sweep + notify | S |
| BUG-036 | save only terminal `executor.py:334-337,291-295`; schema lacks RUNNING `schema.py:256` | crash leaves zero trace of attempt | RUNNING row upfront + per-node append + startup sweep | M |
| BUG-038 | off-list branch returned `llm_decision.py:89-95`; no edge matches `executor.py:318-320` | ok-status with vanished subtrees | fail node or explicit fallback handle | XS |
| BUG-039 | skipped continue w/o NodeResult `executor.py:257-260` | UI can't distinguish branch-skip vs absent | emit skipped NodeResults | XS |
| BUG-040 | full response.text uncapped `http_request.py:65-68` → outputs/node_results/API; no _record_egress call | memory/DB bloat; egress blind spot | size cap/artifact promotion; record egress | S |
| BUG-043 | match by (platform,user) `response_store.py:93-95`; adapters consume next msg `telegram_adapter.py:901-910`, matrix `:377-382`; buttons no allowlist `:1085-1107`; resolve() no identity binding `response_store.py:67-77` | group members' messages swallowed ≤600 s; anyone can press workflow buttons | identity-bind requests; allowlist+requester-bind buttons; expire faster | M |
| BUG-050 | `useApi.ts:70-73` interval no .catch; execute rethrows `:54` | unhandled rejection noise; masked failures | catch → error state/toast | XS |
| BUG-051 | isLoading true per tick `useApi.ts:38`; table gated `BrowserSessions.tsx:184,202` | table remount flicker each 5 s | background-refresh flag (keep old data) | XS |
| BUG-052 | `[tab, refreshKey]` refetch w/o cancellation `Proposals.tsx:33-49`, `Dashboard.tsx:34-48`, `Config.tsx:11-21` | stale response lands last | adopt useApiQuery requestId pattern | S |
| BUG-057 | custom='' init `CronBuilder.tsx:66`; effect onChange('') `:86-92`; empty validates clean `:95-97` | switching to Custom wipes cron silently | initialize from current expr; block empty submit | XS |
| BUG-058 | grep zero ErrorBoundary/componentDidCatch in src | render exception white-screens SPA incl nav | root error boundary + per-page shells | S |
| BUG-067 | isoformat TEXT vs DateTime params across stores; comparisons e.g. style/reflection windows | same-day boundaries wrong depending on writer | normalize via shared helper (pattern: `scheduler.py:405-408`) | M |

## Detailed entries — Low (one-line evidence)

- **BUG-032** `matrix_adapter.py:342-358` startswith("/reset"|"/continue") matches `/resetnow`, `/compactify` → destructive typo hazard; share exact-token parser.
- **BUG-033** `email/adapter.py:537-541` COPY return ignored before `\Deleted`+expunge → draft loss if Sent copy fails; check codes, delete-after-success.
- **BUG-044** `builder.py:322-324` global digit-shape filter drops "2026"/ports from history; scope to auth-code sessions.
- **BUG-062** `telegram_adapter.py:962-981` download-failure path leaks `.ogg` (delete=False, finally unreachable).
- **BUG-063** `:955-956` voice typing sent to sender DM id instead of group chat id; second typing task also opened by engine.
- **BUG-064** allowlist strips `@` on validation (`allowlist.py:66`) but matching compares raw entries (`telegram_adapter.py:654-658`) → configured `@alice` never matches; normalize both sides.
- **BUG-065** Matrix sends verbatim `:159-168`; homeservers reject >~64 KB → long responses fail; port TG chunker.
- **BUG-066** `matrix_adapter.py:64` `_last_edit_times` never evicted (TG prunes) → unbounded on long-lived rooms.
- **BUG-083** `ConfigForm.tsx:71,178-186` Reveal toggles input type over literal asterisks — affordance lies.
- **BUG-084** `Knowledge.tsx:116` `showTrash || true` always includes inactive; toggle client-masks.
- **BUG-053** `useWorkflowEditor.ts:146-147,129-141,204-207` dead AbortController; unguarded loadExecutions setState.
- **BUG-054** `DoctorCheckList.tsx:41-53`, `AuditFindings.tsx:24-33` try/finally no catch; clipboard `TriggerConfigPanel.tsx:186,197`.
- **BUG-085** `BrowserStream.tsx:140,127` memoized connect reads captured canvasSize.
- **BUG-086** `AuthContext.tsx:102-114` deps omit debugLogin read in logout.
- **BUG-087** `NodePropertiesPanel.tsx:367` Number('')===0 defeats min=1; trigger saves skip required checks `useWorkflowEditor.ts:380-394`.
- **BUG-070** `condition.py:100-106` operands evaluated before all()/any().
- **BUG-071** `routes/workflows.py:245-246` free-form trigger_type; no cycle/type validation on save (:346-397).
- **BUG-088** `turn_store.py:213-229` + `message_store.py:186-207` duplicated, caller-free, wrong (session-join, role-collapse).
- **BUG-068** `app.py:409-423` bootstrap flag race (idempotent work duplicated).
- **BUG-045** `execution.py:836-838` pre-tool chatter streamed; `:484-490` DONE swaps in never-streamed 💭 block.
- **BUG-046** `execution.py:831` abort leaves generator suspended in `async with stream` — wrap `contextlib.aclosing`.
- **BUG-079** `types.py:122` declared; sole read `finalization.py:174-176`; no writer.
- **BUG-080** `engine.py:287-291` direct mutation bypasses `_transition` journal.
- **BUG-081** `turn_store.py:95` naive utcnow cutoff vs aware-written column.
- **BUG-082** `routes/scheduler.py:143-205` owner-only checks; admins cannot manage others' tasks (inverse privilege).
- **BUG-072** `history_window_selector.py:88-91` dropped slice includes protected skip_message → over-reported truncation + duplicate tokens post-splice.
- **BUG-073** `store.py:670` `%{query}%` unescaped wildcards.
- **BUG-074** `store.py:722,1061` embedded quotes break tag MATCH.
- **BUG-075** `dedupe.py:236-240`, `llm_dedupe.py:96-100` blobs persisted; no pruning job exists for maintenance_trace.
- **BUG-076** `store.py:664` ORDER BY rank without bm25 column weights.
- **BUG-077** `style/builder.py:130-136` + `vocab.py:12-20` everyday words inflate technical-density ratio labeled formality.
- **BUG-078** confirmation inline-await holds session lock (≤60 s/gated tool, accumulates); `AWAITING_USER` declared `transitions.py:19,24` never emitted.

---

## Reproduction notes (selected high-value)

- **BUG-001:** start a turn with a tool-using prompt; send a second message to the same chat immediately; observe both proceed (add temporary logging at lock acquisition). Deterministic variant: unit test acquiring lock, scheduling second acquirer, then calling release_unused before yielding.
- **BUG-007:** `GET /api/traces?session_ids=a,b` (or failure-store equivalent) → 500 with SQLAlchemy argument error.
- **BUG-011:** save memory containing `"NOT"` then run nightly dedupe pass against it; observe OperationalError traceback.
- **BUG-049:** `cd web-ui && npm run build` → exit non-zero TS2339.
- **BUG-057:** editor → schedule trigger → switch preset to Custom → observe cron field cleared and saved empty.
