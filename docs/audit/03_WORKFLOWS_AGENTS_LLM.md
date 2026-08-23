# Workflow Engine, Agents & LLM Integration Audit

**Audit date:** 2026-08-22 · Scope: `src/hestia/workflows/` (executor, nodes, triggers, stores, interpolation), orchestrator tool loop and streaming, inference client, context construction, policy gate enforcement, subagent delegation, token efficiency.
Bug register: `07_BUGS_RELIABILITY.md`. Security deep-dive: `08_SECURITY_PRIVACY.md`. Architecture context: `01_ARCHITECTURE.md`.

---

## 1. Overall assessment

Two very different quality levels coexist here.

**The chat-agent stack (orchestrator + context + inference) is the strongest part of Hestia**: a journaled turn state machine, five tailored degeneracy circuit breakers, server-truth token counting with layered caches, structured output recovery, confirmation hardening, and typed error taxonomy. Its defects are specific and fixable (streaming honesty, retry dead code, a lock race).

**The workflow engine is the weakest subsystem in the repository.** It has a clean DAG executor with safe expression evaluation and textbook webhook HMAC — but its security posture is broken at the core (tool nodes bypass the trust gate entirely), its execution semantics lack persistence/cancellation/concurrency control, and two trigger types are effectively non-functional (cron) or dangerous (chat-command match-all). The visual editor on top inherits these problems (see `04_FRONTEND.md`/`05_UX_PRODUCT_DESIGN.md`).

## 2. Workflow engine

### 2.1 Execution semantics

`WorkflowExecutor.execute()` runs the entire graph in one awaited call; Kahn topological sort raises on cycles (`executor.py:41-72`). Persisted **only** at end (or fail-fast) via `save_execution`; status vocabulary is `"ok" | "failed"` only — there is no RUNNING state (`schema.py:256`).

Consequences (all Confirmed):

| ID | Finding | Evidence |
|----|---------|----------|
| BUG-036 | Crash mid-run leaves **zero record** of the attempt | `executor.py:334-337` saves only on success |
| BUG-037 | No cancellation, no duration ceiling, no concurrency guard: stalled LLM node or huge interpolated HTTP timeout hangs forever; concurrent triggers run fully parallel; fire-and-forget bus tasks leak | `executor.py:257-309`; `app.py:453-456`; `bus.py:49-55` |
| BUG-004 | `workflow_completed` self-trigger infinite loop: executor publishes with `source_workflow_id=workflow_id` (`executor.py:338-347`) while matching treats missing config as match-all (`triggers.py:266-268`) → a completed-trigger workflow re-executes itself unboundedly, consuming tokens/inserting rows | verified logic |
| BUG-038 | Invalid LLM decision returns the off-list branch value instead of failing → no edge matches → downstream subtrees skipped with `status="ok"`; half the graph silently vanishes | `llm_decision.py:89-95`, `executor.py:318-320` |
| BUG-039 | Skipped nodes emit no NodeResult → UI cannot distinguish "branch not taken" from "never existed" | `executor.py:257-260` |

Fix direction: create a RUNNING execution row upfront and append node results (mirroring the turn journal); add `asyncio.wait_for` ceiling + per-workflow mutex; refuse self-delivery of `workflow_completed`; emit `status="skipped"` results.

### 2.2 Node types

| Node | Validation | Timeout | Security | Key defect |
|------|-----------|---------|----------|------------|
| `tool_call` | tool_name required | none | **NO CapabilityGate** (SEC-001) | Calls `app.tool_registry.call()` directly (`nodes/tool_call.py:54`); gate block unreachable because NODE_TYPES dispatch returns first (`executor.py:366-378`) — verified by direct inspection |
| `investigate` | topic required | none | **NO gate; tools list comes from interpolated inputs** | `nodes/investigate.py:68-70`; tool errors swallowed |
| `send_message` | platform/user/text required | 300s wait | destination resolvable from inputs (SEC-022) | attacker-influenced payload can pick recipient when author left it unpinned (`send_message.py:39-52`, `_resolve` prefers inputs) |
| `http_request` | url required | config/input default 30s | SSRFSafeTransport ✓ but no egress audit; response size uncapped into outputs+DB+API | BUG-040 |
| `condition` | expr required | n/a | AST-whitelisted eval — genuinely safe mini-language ✓ | boolean ops evaluate eagerly (`all()/any()` after full operand eval) → NameError where Python would short-circuit |
| `inference` (legacy) | prompt defaults to `str(inputs)` | chat default | quirky | if reasoning contains any URL, whole answer replaced by first URL (`executor.py:400-404`) |

### 2.3 Triggers

- **BUG-005 (High): cron schedule triggers don't actually schedule.** The sole publisher of `schedule_fired` is the scheduler engine firing an *unrelated task* (`scheduler/engine.py:172-181`); trigger matching then samples `croniter.match(cron, now)` at that instant. A `*/5 * * * *` workflow fires only if some other task happens to fire within that exact minute — with no other scheduled tasks, **it never fires**. Additionally `if cron is None: return True` makes a cron-less schedule workflow execute on every system-wide event. Fix pattern already exists in-repo: memory maintenance registers itself as first-class SchedulerStore tasks (`maintenance/scheduler.py:33-90`).
- **SEC-021:** chat-command triggers match-all when `command` unset (`triggers.py:176-178`) — any user's any slash-command fires them, with the raw message text flowing into interpolation/prompts (prompt-injection surface).
- Webhook HMAC is exemplary (constant-time compare, ±300s window, reveal-once secrets, sentinel round-trip through edits). Replay dedup is process-local/evictable (SEC-017).

### 2.4 Versioning, secrets, test runs

Activation is atomic (deactivate siblings + activate target in one transaction, `store.py:292-330`). Webhook secrets properly redacted. Gaps:

- **BUG-041 (High): test runs execute production side effects** — real sends, ungated tools, results polluting the production executions table that feeds "last execution status" (`routes/workflows.py:477-482`). No dry-run, no `is_test` flag, no isolation marker.
- **SEC-014:** node-config secrets get no redaction in the versions API — an API key pasted into http headers config is exposed verbatim to anyone with read access.
- No save-time validation: cycles/unknown types/bad expressions surface only at run time; `trigger_type` free-form on update (typos silently disable triggering).

### 2.5 Interpolation

Regex-based `\{\{\s*([\w.]+)\s*\}\}` — safe (no eval). Defects (BUG-039 register / UX-013): missing keys resolve to `""` **silently**; dict/list values render as Python repr (`{'a': 1}` — single quotes) which corrupts JSON templates built by concatenation; no numeric/list indexing; no default filters. Combined with BUG-039's invisible skips, users get `status=ok` executions whose payloads are quietly wrong.

## 3. Policy enforcement map (the key deliverable)

Every path that invokes a tool handler, and whether it passes `CapabilityGate.check`:

| # | Path | Gated? | Evidence |
|---|------|--------|----------|
| 1 | Orchestrator loop (CLI/TG/MX/scheduler/subagent turns) | **YES** — gate runs before confirmation/auto-approve; meta-tool `call_tool(name="terminal")` unwrapped so inner tool is checked | `execution.py:1458→1538→1687`, `_meta_call_tool:1620-1638` |
| 2 | Policy-triggered delegation ("research…") | **NO** — calls destructive-classified `delegate_task` directly, no killswitch/injection escalation/audit | `execution.py:694-709 → :1410` (SEC-003) |
| 3 | Explicit `delegate_task` tool call | YES (via #1); subagent inner turns gated again w/ SUBAGENT channel | `delegate_task.py:173`, `app.make_orchestrator` |
| 4 | Scheduler tasks | YES via #1 + filter_tools strips shell/write/email + auto_approve fail-closed blocklist | `default.py:225-244,297-305` |
| 5 | Workflow fallback nodes (node.type names a registered tool) | YES — synthetic actor, WORKFLOW channel, allow_list from workflow | `executor.py:413-434` |
| 6 | Workflow `tool_call` node | **NO** | `nodes/tool_call.py:54` (SEC-001) |
| 7 | Workflow `investigate` node | **NO** | `nodes/investigate.py:70` (SEC-001) |
| 8 | Truncated-write recovery | **NO** — raw handler invocation; writes even while context injection-flagged; skips killswitch/confirmation/audit (path sandbox still applies incidentally) | `quality.py:199-201` (SEC-004) |

Dead controls discovered by this map: `workflow.trust_level` (stored, API-validated, rendered in UI — never read by the executor); `TrustConfig.scheduler_shell_exec` etc. (the orchestrator never passes an allow-list to the gate, so these always deny `not_allow_listed` while `filter_tools` still advertises the tools — confusing denials + digest noise); `Channel.SUBAGENT` in neither trusted nor unattended set (destructive calls approved unless capability-stripped; `browser_login` carries no capability label so it never is); gate's `auto_approved` verdict computed then discarded, re-derived divergently in the orchestrator.

**Root cause and fix:** enforcement lives at one call site by convention; the registry — the actual chokepoint — does nothing. Move enforcement into/wrapping `ToolRegistry.call` (registry holds a gate reference; ungated internal callers pass an explicit, audited system context). Keep the gate for decisions. This converts four bypasses and all future ones into impossibilities. Regression test: paranoid-preset workflow invoking `terminal` must be denied.

## 4. Context management & prompt construction

Composition order (verified): identity/SOUL prefix → capabilities prefix (deployment self-awareness) → memory epochs → protected history (first user message pinned) → budget-windowed history → style guidance → current message. Strengths worth preserving:

- Tokenize cache keyed to exclude reasoning content; bounded LRU (4096); content-hash keys for prefixes make invalidation automatic; `tokenize_batch` separator trick with four correct fallback paths (`core/inference.py:384-427`, `context/builder.py:506-508`).
- Loop-collapse keeps one copy of repeated pairs **and** injects an explicit SYSTEM NOTE telling the model what was removed (`builder.py:285-303`).
- Protected-context overflow degrades into a session handoff with actionable user guidance instead of a raw error (`finalization.py:187-225`).

Defects:

| ID | Finding | Evidence |
|----|---------|----------|
| BUG-042 (High) | Multi-tool turns: shared assistant double-counted against budget; sibling tool result vanishes from both included history and dropped-history accounting (invisible to compressor) | `history_window_selector.py:76-79` advances `i += len(pair_msgs)` instead of `j+1` |
| BUG-028 (Med) | Compression splice bypasses sequence validation; retry `pop(0)` can orphan a tool message → strict-template 400s at request time | splice after validation at `builder.py:465-477`; `compressed_summary_strategy.py:62-82` |
| BUG-031 (Med) | Epoch composition loads the entire memory table per session start (no LIMIT; Python-side cap after materializing); cost grows linearly with lifetime memories to select ≤500 tokens | `store.py:585-613`; `epochs.py:88-118` |
| BUG-044 (Low) | Auth-code filter drops ANY all-digit 4–10 char user message globally ("2026", port numbers vanish from history, breaking follow-ups) | `builder.py:322-324` |
| PERF-003 | Full history re-tokenized over HTTP every tool-loop iteration instead of caching per-message counts | `builder.py:422-450` |
| PERF-007 (cross) | calibration.json records model name but loader ignores it — model swap silently mis-budgets | `builder.py:161-192` |

Memory-store scoping deserves special mention: `search()` fails closed on missing identity (good, verified claim), but `list_memories`, `delete()`, `soft_delete()`, `update()`, pin/mark_* **fail open** — scope clause added only when both platform AND platform_user present (`store.py:735` etc.). Cross-user reads/deletes possible for any caller that omits identity (SEC-010). Maintenance passes call `search()` with raw memory excerpts unprotected against FTS5 syntax errors (BUG-011).

## 5. Streaming & LLM integration

- Streaming pipeline is Telegram-only end-to-end (adapter stream callback → rate-limited edits → final edit with fallback). Matrix gets nothing (silent no-op with `stream=true`).
- **BUG-003:** mid-stream stall → fake `"stop"`, silent truncation (asymmetric with non-streaming FAILED/retry).
- **BUG-022:** SSE server error objects ignored by parser → slow timeout masquerading as truncation.
- **BUG-045:** pre-tool chatter is streamed to the user even when the stream ends `finish_reason="tool_calls"`; at DONE the final edit injects a 💭 reasoning prefix that was never streamed — jarring content replacement mid-conversation (`execution.py:484-490,836-838`).
- **BUG-046:** mid-stream abort leaves the SSE generator unclosed inside `async with client.stream(...)` — wrap in `contextlib.aclosing` (`execution.py:831`, `inference.py:635-687`).
- **PERF-004:** no `stream_options: {"include_usage": true}` → trace token columns null on all streaming turns; accounting unreliable exactly where volume is highest.
- Connection-drop diagnosis is good post-fix: TransportError → `InferenceConnectionError(operation, detail)` with correct exception-ordering, surfaced verbatim in finalization messages (audited commit verified).

## 6. Agentic behavior: tool loop, degeneracy defense, quality passes

The loop (≤ `max_iterations`, ≤ `max_tool_calls_per_turn`) is defended by five complementary circuit breakers: identical-call repetition blocking, schema-dropping after malformed-call streaks, correction-message injection, thinking-budget abort+nudge (streaming only — BUG-020), and regression fixture capture at each failure site. A four-format text parser recovers tool calls the structured channel lost. This is the most thoughtful degeneracy handling this auditor has seen in a project this size.

Weak spots:

- **BUG-024:** greeting/error substring heuristics false-positive on legitimate replies ("Hi Dylan, here's…" ⇒ "You lost context").
- **BUG-021:** transient-inference retry policy dead code (except clause too narrow; backoff ignored) → transient llama-server blips become immediate FAILED turns.
- **BUG-025:** rollback restores files only; checkpoints die with the process; git stash-pop conflict-prone with swallowed failures.
- **BUG-078:** confirmation escalation awaits inline while holding the session lock (≤60s per gated tool, sequential gated tools accumulate); declared `AWAITING_USER` state never emitted, so approval pauses are invisible in traces.
- Subagents: throwaway sessions, fresh gated orchestrator, recursion blocked twice, archived in finally — reasonable isolation. Result summaries trusted verbatim into parent context (re-scanned as tool results next dispatch — acceptable). Timeout loses artifact refs and can strand half-written files.

## 7. Failures, retries, cancellation — summary matrix

| Layer | Retry | Cancellation | Persistence of in-flight state | Verdict |
|-------|-------|--------------|-------------------------------|---------|
| Chat turns | Degeneracy corrections yes; transient-inference retries dead (BUG-021) | None (new messages queue on lock; `/reset` doesn't cancel — BUG-023) | Journaled transitions + stale-turn recovery at startup only (BUG-035) | Good bones, gaps at edges |
| Scheduled tasks | Constant 30s forever (BUG-012) | None | next_run pre-dispatch = skip-on-crash (BUG-030) | Weakest background loop |
| Workflows | None anywhere | None (BUG-037) | Nothing until terminal (BUG-036) | Needs execution lifecycle |
| Memory maintenance | Weekly cadence; one judge error aborts pass (BUG-026) | N/A | Soft-delete + undo + trace ✓ | Strong design, fragile execution |

## 8. Token/inference efficiency opportunities (ranked by expected saving)

1. **Cache per-message token counts across loop iterations** — today every iteration re-tokenizes full history + probes over HTTP (`builder.py:422-450`). Largest recurring saving; multiplies with max_iterations.
2. **Request `include_usage` on streams** — restores token accounting truthfulness (free).
3. **Drop consumed meta-tool schema dumps from history** — `describe_tool`/`list_tools` payloads persist forever; mirror the existing schema-drop mechanism.
4. **Maintain breaker state on TurnContext** — replace O(history) rescans per dispatch (`execution.py:240-259,1054-1061`).
5. **Incremental rebuilds for correction/nudge iterations** — appending one message rebuilds everything today.
6. **LIMIT epoch queries** (~200) instead of full-table materialization per session start (BUG-031).
7. **Calibrate envelope overhead once** — the correction hook exists; count_request tokenizes full JSON body each build.

## 9. What's done well (preserve)

1. Turn journaling + explicit transition table — crash forensics proved themselves in the Aug-13 llama-crash investigation.
2. Degeneracy circuit breakers with tailored corrections and captured regression fixtures — not generic retries.
3. Server-truth token counting + cache design — best-engineered subsystem in the repo.
4. AST-whitelisted condition language in workflows — template-injection-proof by construction.
5. Confirmation flow hardening — requester binding, double-submission safety, dual timeout coverage, fail-closed defaults.
