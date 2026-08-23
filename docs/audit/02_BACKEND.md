# Backend Audit — Hestia

**Audit date:** 2026-08-22 · Scope: `src/hestia` platforms, persistence, orchestrator, tools runtime, app/serve lifecycle. Security findings live in `08_SECURITY_PRIVACY.md`; performance measurements in `06_PERFORMANCE.md`; the full bug register with severity/confidence is `07_BUGS_RELIABILITY.md`. This document is the backend narrative.

---

## 1. Overall assessment

The backend is **architecturally disciplined but operationally leaky**. The state machine, persistence split, and token engineering are genuinely well built. The recurring weaknesses are: (a) concurrency primitives with subtle races (session locks, slot eviction), (b) fire-and-forget background work without lifecycle management, (c) silent failure as the default error strategy, and (d) duplicated logic that has already produced divergent behavior between Telegram/Matrix and two broken copies of a shared SQL pattern.

Findings below use IDs registered in `07_BUGS_RELIABILITY.md`.

## 2. Concurrency and async correctness

### BUG-001 — Session-lock pop race breaks per-session serialization (Critical · Confirmed by inspection)

`SessionLockManager.release_unused` (`orchestrator/lock.py:40-51`) pops the dict entry whenever `lock.locked()` is False. But an `asyncio.Lock` reports unlocked between `release()` and the moment a waiter's coroutine resumes. `engine.process_turn` calls `release_unused` synchronously immediately after the `async with lock:` block exits (`engine.py:320`; same call in `platforms/runners.py:182`):

1. Turn A finishes; `release()` wakes pending waiter B (B holds a reference; `_locked` still False).
2. A calls `release_unused` → entry popped from `_locks`.
3. Turn C arrives → `acquire()` creates a **fresh** lock → proceeds immediately.
4. B resumes on the orphaned object → B and C run concurrently on one session.

This silently voids ADR-041 (per-session turn serialization), which message ordering, slot save/erase pairing, and stream-state handoff all depend on. `is_locked()` probes (`scheduler/engine.py:139`, `compaction.py:73`) also read stale dict state. No error is ever logged. Fix direction: never prune while waiters exist (track waiter count), or replace pop-pruning with refcounted acquisition.

### BUG-002 — Slot eviction I/O runs outside the pool lock (High · Highly likely)

`slot_manager.py:289-302` deletes the assignment, releases the pool lock, then awaits `slot_save`/`slot_erase`. A concurrent `acquire()` can claim the freed slot mid-save/mid-erase — snapshots cross-contaminate and a new owner's KV cache can be erased underneath it. Compounding: `finalization.py:127-131` erases by `session.slot_id` without re-checking ownership. This is not theoretical: the operator's own crash forensics (`runtime-data/logs/llama-crash-forensic-2026-08-13.md`) show llama-server SIGABRT during exactly these slot-operation interleavings (upstream cuBLAS bug, but the trigger is concurrent slot ops).

### BUG-006 — Telegram processes updates sequentially; one slow turn blocks every chat (High · Highly likely)

python-telegram-bot defaults to sequential handler execution; no `concurrent_updates` anywhere in `src/`. Handlers fully await `process_turn` — LLM inference, tool loops, up-to-60s confirmations, plus two ffmpeg subprocesses for voice. One long turn stalls all users/chats including `/start` and callback queries. Fix: enable `concurrent_updates` + rely on the (post-fix) session lock for correctness.

### BUG-030 — Scheduler tick head-of-line blocking; at-most-once cron across crashes (Medium · Confirmed)

`_tick` holds `_tick_lock` while awaiting a full turn (`scheduler/engine.py:132,150-151`); one slow scheduled task delays every other due task. `next_run_at` is written **before** dispatch, so a mid-turn crash permanently skips that occurrence. Also BUG-012's constant 30s retry means a deterministically failing task hammers forever.

### BUG-029 — EventBus fallback destroys its own handler tasks (Medium · latent)

`events/bus.py:66-68`: the no-running-loop branch of `publish_nowait` runs `asyncio.run(self.publish(...))`, which tears down the loop with handler tasks pending ("Task was destroyed but it is pending"). Currently unused in `src/`, but it is a landmine for any future sync caller.

Other async hygiene is good: contextvars are set/reset in `finally` (`runners.py:334-338`), Matrix sync loop backs off instead of dying (`matrix_adapter.py:311-315`), terminal tool kills the whole process group on timeout (`terminal.py:72-88`).

## 3. Platform layer

### Divergence bugs (Matrix vs Telegram)

- **BUG-032** — Matrix command dispatch uses prefix matching: `startswith("/reset")` matches `/resetnow`, `/compactify` etc. (`matrix_adapter.py:342-358`). Telegram requires exact commands. A typo on Matrix can destructively archive a session.
- **BUG-013** — Matrix's initial blocking `sync(timeout=5000)` has no error handling (`matrix_adapter.py:129`); a transient homeserver outage at boot raises through `asyncio.gather(*tasks)` (`serve.py:154-155`) and **terminates every platform**, not just Matrix. The steady-state loop backs off correctly.
- Reset semantics diverge: Telegram pays an LLM summarization per reset and carries a real summary forward; Matrix plants a fixed `[RESET]` marker and starts clean (`telegram_adapter.py:708` vs `matrix_adapter.py:431-435`).
- Streaming exists only on Telegram; Matrix has edit support but no stream callback, so `inference.stream=true` silently does nothing on Matrix.
- Message chunking exists only on Telegram (3800 chars); Matrix sends verbatim and homeservers reject >~64KB events — very long responses fail outright on Matrix.
- Matrix's edit rate-limit dict never evicts entries (`matrix_adapter.py:64`) — unbounded growth on long-lived rooms (Telegram prunes its copy).

### Message-handling bugs

- **BUG-043** — Workflow response interception matches only `(platform, platform_user)` (`workflows/response_store.py:93-95`); adapters feed the *next* message as the answer (`telegram_adapter.py:901-910`, same in Matrix). In groups, **any allowed member's next message — even one addressed to someone else — is silently swallowed** as the workflow answer for up to 600s. Inline `workflow:` buttons have **no allowlist check at all** (`telegram_adapter.py:1085-1107`) and `resolve()` performs no identity binding (tool confirmations *are* requester-bound — the asymmetry looks accidental).
- **BUG-014** — Voice turns bypass `PlatformRunner.on_message` (`telegram_adapter.py:1061-1070`): ContextVars unbound → confirmation-requiring tools are auto-denied during voice turns; channel misattributed as CLI (`execution.py:1512` fallback); workflow interception and unknown-sender rejection skipped.
- **BUG-015** — Confirmation prompts render raw tool JSON with `parse_mode="Markdown"` and no parse-failure fallback (`telegram_adapter.py:604-632`). Unbalanced markdown entities in arguments → `BadRequest` → gated tools fail spuriously. The model-facing path escapes correctly; this path doesn't use it.
- **BUG-016** — Multi-chunk edit fallback duplicates content or silently drops trailing chunks: "message is not modified" marks success while skipping `chunks[1:]`; later-chunk failures resend *all* chunks including the already-edited first (`telegram_adapter.py:391-439`). Retry budget: exactly one RetryAfter retry per API call.
- **BUG-034** — Rate-limited sessions receive two near-identical notifications: engine notifies via callback then raises `PlatformError`, which the runner also surfaces (`engine.py:222-226`, `runners.py:331-333`).
- Voice temp-file leaks on download failure (`delete=False`, cleanup `finally` unreachable, `telegram_adapter.py:962-981`); typing indicator targets the sender's DM id instead of the group chat during voice (`:955-956`).

### Email adapter

- **BUG-017** — Poison-message infinite redelivery: mark-read happens after publish; a persistently failing message retries every 30s forever, refiring `email_received` triggers (`email_inbound.py:76-90`). No dead-letter/backoff.
- **BUG-018 / PERF-012** — `list_messages` fetches INTERNALDATE per UID (one IMAP round-trip per message before applying `limit`) and falls back to treating UIDs as Unix epochs (`email/adapter.py:319-332`) — corrupting sort order for any mailbox where that branch fires.
- **BUG-033** — `send_draft` ignores COPY result codes before flagging `\Deleted` + expunging: if the Sent copy fails, the draft is destroyed (`email/adapter.py:537-541`); same unchecked pattern in `move_message`.
- Allowlist normalization mismatch: validation strips `@` from usernames but matching compares raw config entries, so `allowed_users=["@alice"]` passes startup checks yet never matches — silent denial (fail-closed direction).

## 4. Persistence layer

Measured against the live database (`runtime-data/hestia.db`, 20MB): `journal_mode=delete`, `foreign_keys=0`, **no index on `messages`** (7430 rows, hottest table).

- **BUG-008 / PERF-006** — No SQLite tuning: FKs off (orphan-prone), no WAL (readers block writers under load), no `busy_timeout` (concurrent writes raise "database is locked" unhandled). All three fixable in `Database.connect`.
- **BUG-007** — Trace/failure store list queries build an `IN` clause via string interpolation into `sa.text()` without expanding bindparams (`trace_store.py:116-137`, `failure_store.py:116-137`) → SQLAlchemy tuple-binding crash when filtering by sessions. Two of four duplicated WHERE-builders carry the bug; a shared helper would have fixed it once.
- **BUG-009 / F4** — PostgreSQL path is broken in practice: migration m006 uses SQLite-only `pragma_table_info` unguarded (`migrations/__init__.py:194-202`) → startup crash on PG; raw-SQL `isoformat()` timestamp strings are incompatible with asyncpg typed parameters in trace/failure/capability/user stores.
- Timestamp format fragmentation: some stores write `datetime.isoformat()` strings into TEXT, others bind DateTime params; comparisons across formats produce wrong same-day boundaries (style/reflection scheduling windows).
- **Retention:** nine tables have no pruning anywhere (traces, capability_events, egress_events, maintenance_trace — which embeds full merged-content blobs — compaction_archive, turn_transitions…). `list_egress` dumps the full table per request. Live data is small today; growth is unbounded by design.
- **DDL drift:** three sources of truth (schema.py, raw-DDL shims in `failure_store.create_table` and `maintenance_trace_store.create_table`, Alembic). Alembic never covered most current tables (users, workflows, topics, capability_events…) — autogenerate would emit a giant diff. m002 created columns nullable that schema.py declares NOT NULL.
- Dead code: `get_turn_messages` implemented twice (`turn_store.py:213`, `message_store.py:186`), zero callers, both wrong (join by session_id only, collapses to last-per-role); deprecated `sessions.py` facade; `Database.execute()` wrapper unused.
- Done well: TOCTOU-safe get-or-create via partial unique index + IntegrityError retry (with race tests); atomic compaction transaction; ErrorResolutionStore is the model citizen (proper expanding bindparams, upsert, the only retention job); secret scrubbing before capability-event persistence; migration framework idempotent-in-one-transaction.

## 5. Orchestrator / inference reliability

- **BUG-003** — Mid-stream stall is converted to a fake successful stop: `TimeoutError` inside the streaming loop sets `finish_reason="stop"` and proceeds down the DONE path (`execution.py:800-817`) — user receives a truncated answer with no truncation marker. The non-streaming path raises `InferenceTimeoutError` → FAILED/retry. Same server condition, opposite outcomes.
- **BUG-022** — SSE parser inspects only `data:` lines and treats empty-`choices` chunks as usage-only; server `{"error": ...}` payloads fall through every branch (`inference.py:656-674`) → immediate rejections stall until the 120–180s inactivity timeouts, then masquerade as BUG-003 truncation.
- **BUG-020** — Thinking budget enforced only when streaming: `ThinkingBudgetExceededError` raised solely in `_run_inference_streaming`; non-streaming burns up to `max_tokens` of reasoning unchecked, and the thinking-abort nudge machinery is dead code with `stream=false`.
- **BUG-021** — Transient-inference retry policy is dead code: policy maps `InferenceTimeoutError`/`InferenceServerError` to RETRY_WITH_BACKOFF(1.0s), but the except clause catches only `ThinkingBudgetExceededError`; transient errors propagate straight to FAILED; `backoff_seconds` ignored everywhere.
- **BUG-019** — Crash window bricks sessions: assistant message persisted before tool results (`execution.py:402-404` vs `:718-721`); a crash between leaves dangling `tool_calls` with no following `tool` messages, which strict chat templates reject with 400s until manual DB surgery. Builder performs no repair on load.
- **BUG-025** — `rollback_turn` restores files only; DB messages/slot/artifacts survive rollback while disk reverts, and checkpoints live in an in-memory dict — post-crash rollback reports "No checkpoint found". Git path uses `stash pop` (applies-and-drops; conflict-prone; failures swallowed leaving orphaned stashes).
- **BUG-024** — Quality heuristics false-positive: `_is_greeting_mid_task` fires when a reply merely *starts with* a greeting at iteration >2 ("Hi Dylan, here's the summary…" ⇒ "You lost context"); `_looks_like_error` substring-matches benign grep output toward PATCH_FAILED classification.
- **BUG-035** (register ID) — recover_stale_turns is startup-only; hung turns stay non-terminal until restart; recovery neither notifies users nor reconciles file state.
- Misc: `total_reasoning_tokens` declared, read, never written (traces always null); illegal-transition handler mutates state without journaling (`engine.py:287-291`); naive-vs-aware datetime comparison in the stale-turn cutoff (`turn_store.py:95`).
- Done well: explicit transition table + journaling; five tailored degeneracy circuit breakers (loop detection, schema-drop signal, correction injection, regression fixture capture); four-format text parser recovering structured tool calls; honest server-truth token counting.

## 6. Tools runtime & resource management

- Terminal output buffered unbounded in RAM until completion (`proc.communicate()`) — `cat /dev/urandom | base64` accumulates gigabytes within the window; model-controlled `timeout` unclamped; environment fully inherited so `printenv` pulls host secrets into model context (see SEC-015).
- Filesystem tools: `write_file` non-atomic direct truncate-write (no temp+`os.replace`, unlike ArtifactStore which does it correctly); `edit_file` reads uncapped; `read_file` loads the entire file into memory before slicing to `max_bytes` (OOM vector on huge files in allowed roots). Path sandbox itself is solid (resolve + relative_to defeats traversal/symlinks; residual check-then-open TOCTOU only).
- Artifacts: GC invoked only from admin CLI; TTL lazy at read; orphaned `.bin` files when crash hits between payload and metadata writes; inline artifacts stored in one JSON rewritten wholesale on every store/delete (quadratic I/O over time). Live dir already 67MB.
- Sync artifact reads inside async paths block the event loop (`executor.py:438`, `nodes/tool_call.py:56`).
- Browser session stores write cookies/localStorage world-readable (no chmod) and launch Chromium `--no-sandbox` while rendering untrusted pages (SEC-016).

## 7. Lifecycle (startup/shutdown)

- Bootstrap: check-then-await race on `_bootstrapped` flag (`app.py:409-423`) — benign today because create_all+migrations are idempotent, but sloppy.
- Shutdown: `cmd_serve` monkey-patches `app.inference.close = _noop_close` to keep platform runners from closing the shared client (`serve.py:34`) — brittle method-assign; if anything captured the bound method earlier, it closes anyway.
- One platform task crashing propagates through `gather(*tasks)` and kills serve entirely (`serve.py:154-155`) — see BUG-013.
- Trigger registry never stopped on shutdown; email adapter closed via neither runner path nor `app.close()` in `run_platform` (only inference is).
- Web context is a module-global singleton (`set_web_context`) — test contamination risk, hidden coupling.
- Startup posture guard (C1/C3 hard-fail with actionable messages) is genuinely good engineering; it misses only `debug_login` (SEC-006).

## 8. API surface notes

FastAPI routes are consistently layered (middleware → require_admin → owner checks), with specific gaps documented in `08_SECURITY_PRIVACY.md` (login recipient injection SEC-002, topic IDOR SEC-007, dashboard cross-user leak SEC-008, scheduler inverse-privilege BUG-04x, unbounded list endpoints PERF-013). Config PUT intentionally returns 501 — no mass-assignment surface. Static serving and SPA catch-all are traversal-safe. No exception handlers registered: FastAPI defaults return opaque 500s without stack traces (good), with deliberate `detail=str(exc)` sites being the only verbose channels (auth routes disclose platform configuration state to anonymous callers).

## 9. Highest-value backend fixes (order)

1. BUG-001 lock race (+ waiter-aware prune) — restores the core invariant.
2. SEC-001 gate chokepoint move (registry-level enforcement) — eliminates the class.
3. BUG-002 slot eviction locking.
4. BUG-007 + BUG-009 persistence query fixes (small diffs, real breakage).
5. BUG-008 SQLite pragmas (WAL, busy_timeout, FKs) + PERF-005 messages index.
6. BUG-003/BUG-022 streaming honesty pair (raise or mark truncated; detect SSE errors).
7. BUG-012 exponential backoff + max attempts.
8. BUG-006 Telegram concurrent_updates.
