# Performance Audit — Hestia

**Audit date:** 2026-08-22 · Scope: backend, database, frontend, workflow execution, model usage, tools, startup, memory/resources.
Method: direct measurement where possible (live DB pragmas/schema, production build output, live data volumes); code-path tracing elsewhere. Each finding is labeled **Measured**, **Confirmed by code**, or **Suspected**.

---

## 1. Measured findings

### PERF-001 — Frontend ships one 2.74 MB JS chunk (800 KB gzip) · Measured · High impact
`npx vite build`: `index-*.js` 2,739.79 kB / 800.26 kB gzip (+ CSS 74.95 kB / 12.02 kB gzip). Vite emits the >500 kB warning. React Flow and the entire component library load even on Login/Dashboard. No route-level code splitting, no vendor chunks.
**Fix:** `React.lazy` per page + `manualChunks` for reactflow; drop `@openuidev/react-ui` (PERF-002, used only for theme scaffolding while all components are bespoke). Expected: 60–70% initial-bundle reduction.

### PERF-006 — SQLite runs with default journal (`delete`), no WAL · Measured on live DB · Medium impact
Live `runtime-data/hestia.db`: `journal_mode=delete`, `foreign_keys=0`, no `busy_timeout`. Readers block writers; concurrent writes raise "database is locked" unhandled. At today's scale (20 MB) this is tolerable; under concurrent platform+scheduler+maintenance writes it is a latency and error source. One-line-ish fix in `Database.connect`.

### PERF-005 — `messages` table has no index; every turn scans it · Measured (live schema) · Medium impact
Index inventory from the live DB contains zero `messages_*` indexes; `schema.py` declares none. Context building runs `SELECT … WHERE session_id=? ORDER BY idx` plus `max(idx)` probes per append and per rebuild — full scans of the hottest table (7,430 rows live, growing). Also missing: `sessions.last_active_at` ordering index. Fix: add `(session_id, idx)` and `(state, last_active_at)` indexes via an idempotent runtime migration.

### Data volumes & growth · Measured · watch item
messages 7,430 · turn_transitions 12,825 (~19× turns) · compaction_archive 1,022 · traces 631 · egress_events 778 · artifacts dir 67 MB. Nine tables have no retention job anywhere; `maintenance_trace` embeds full merged-content blobs. Growth is linear-to-superlinear by design with no ceiling.

### Test suite cost · Measured · fine
2,272 tests in ~260 s, deterministic across four runs — healthy CI economics; no action needed.

## 2. Model/inference usage efficiency (Confirmed by code)

### PERF-003 — Full context re-tokenized every tool-loop iteration · High cumulative impact
Each iteration of the tool loop calls `builder.build()`, which re-tokenizes the *entire* history plus protected-body/join-overhead probes over HTTP to llama-server (`context/builder.py:422-450`). With max_iterations=10 and growing histories, later iterations pay repeated multi-thousand-token tokenize round-trips for unchanged content.
**Fix:** cache counts keyed by message identity/content hash (the cache infrastructure exists); tokenize only deltas. Largest recurring CPU/network saving in the hot path.

### PERF-004 — Streaming requests never request usage · free win
No `stream_options: {"include_usage": true}` in `chat_stream` (`inference.py:619-626`) → trace token columns null on streaming turns; accounting blind where volume is highest.

### PERF-014 — Breaker state rescanned O(history) per dispatch · Low-Med
`_latest_tool_result_categories` and prior-describe scans walk full history each iteration (`execution.py:240-259,1054-1061`). Maintain running state on TurnContext.

### PERF-015 — Consumed meta-tool payloads persist forever · Med (tokens = money/latency)
`describe_tool`/`list_tools` schema dumps stay in history permanently after consumption; correction/nudge iterations rebuild the entire context after appending one message. Both mirror existing mechanisms (schema-drop, incremental build) that just aren't applied here.

### PERF-016 (cross BUG-031) — Epoch composition loads the whole memory table per session start
Global + topic epoch queries have no LIMIT; Python-side capping after materializing everything (`store.py:585-613`, `epochs.py:88-118`) — cost grows linearly with lifetime memories to select ≤500 tokens. Add LIMIT ~200.

### Token-budget accuracy risks
Calibration file records the model it was measured against but the loader ignores the field (`builder.py:161-192`) — a model swap silently mis-budgets every turn (over-truncation or overflow retries). `total_reasoning_tokens` is never written, so thinking-heavy models' true cost is invisible in traces.

## 3. Backend resource efficiency (Confirmed by code)

| ID | Finding | Evidence | Impact |
|----|---------|----------|--------|
| PERF-011a | `read_file` loads entire file into RAM before slicing to `max_bytes` | `read_file.py:55` | OOM vector on huge files in allowed roots |
| PERF-011b | Terminal stdout/stderr buffered unbounded until completion | `terminal.py:79` `proc.communicate()` | GB accumulation within timeout window |
| PERF-010 | Inline artifacts stored in one JSON rewritten wholesale per store/delete (all payloads base64 in memory) | `store.py:130-139` | Quadratic I/O + corruption blast radius as inline set grows |
| PERF-012 | Email listing does one IMAP FETCH per matched UID before applying limit | `email/adapter.py:319-332` | Tens of thousands of RTTs on large mailboxes |
| PERF-013 | Unbounded API endpoints dump whole tables (`list_egress` has no limit param at all; scheduler tasks/topics/users unpaginated) | `trace_store.py:216-221`, routes | Latency spikes + response-size blowups as tables grow |
| PERF-017 | Sync artifact reads inside async paths block the event loop | `executor.py:438`, `nodes/tool_call.py:56` | Stalls all concurrent work during large-artifact reads |

## 4. Concurrency-as-throughput issues (cross-refs)

- **PERF-008 (=BUG-006):** Telegram sequential update processing serializes *all* chats behind one slow turn — the dominant real-world latency source for multi-chat operation. Enabling `concurrent_updates` (with the session-lock fix first) is the biggest perceived-performance improvement available on chat surfaces.
- **PERF-018 (=BUG-030):** scheduler tick holds its lock through full turns → due tasks queue behind each other; bounded-concurrency dispatch would decouple.
- Workflow executions run unbounded parallel (no mutex/debounce) — not a throughput bug today, but a token-cost multiplier under trigger storms (self-trigger loops).

## 5. Startup & lifecycle

Lazy `cached_property` composition keeps startup cheap (verified design; eager stores only). Migrations idempotent-in-one-transaction. Two minor items: bootstrap flag check-then-await race (benign duplicate work); Matrix boot-sync failure kills serve (availability rather than perf). No expensive import-time work found in the hot packages.

## 6. Frontend rendering

- Poll flicker churn: sessions table unmount/remounts every 5 s tick via isLoading toggling skeleton (B13/PERF-009) — wasted DOM churn and visible flicker.
- WebSocket mousemove flood without throttle/coalescing (`BrowserStream.tsx:251-254`) — bandwidth/CPU on remote sessions.
- Minor rerender hotspots (toast provider value, editor callback deps) — cosmetic today.
- No virtualization anywhere; current caps (memories ≤100/page, executions ≤50) make that acceptable — revisit only if limits grow.

## 7. Perceived performance (product-level)

1. Streaming progressive delivery already exists on Telegram and is well-tuned (20-char/500 ms buffers, 1.5 s edit cap) — preserve.
2. The single-chunk SPA means first paint waits on 800 KB gzip; route-splitting fixes Login/Dashboard time-to-interactive most.
3. Head-of-line blocking (PERF-008/018) converts one slow LLM call into visible delays everywhere — fixing concurrency fixes perceived speed more than any micro-optimization.
4. Silent truncation/fake-stop (BUG-003) makes responses *feel* complete when they aren't — worse than slowness for trust.

## 8. Priority order (impact × confidence ÷ effort)

1. PERF-008/BUG-006 Telegram concurrent updates (+ lock fix prerequisite) — biggest user-visible latency win.
2. PERF-001/002 bundle split + dependency drop — biggest frontend win, low risk.
3. PERF-003 delta tokenization — biggest hot-path compute/network win.
4. PERF-005 messages index + PERF-006 WAL/busy_timeout — two small migrations, durable scaling headroom.
5. PERF-004 include_usage — free correctness-of-accounting.
6. RETENTION jobs for the nine unbounded tables — prevents the slow-motion problem.
