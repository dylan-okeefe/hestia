# Hestia Architecture Audit

**Audit date:** 2026-08-22 · **Worktree:** `~/Hestia-runtime` (runtime branch @ `4388cc9c`)
Companion documents: `02_BACKEND.md`, `03_WORKFLOWS_AGENTS_LLM.md`, `04_FRONTEND.md`, and the finding register in `07_BUGS_RELIABILITY.md`.

---

## 1. What Hestia is

Hestia is a **local-first personal AI assistant** that runs on the operator's own hardware (Ubuntu + NVIDIA GPUs, llama.cpp inference). It connects to chat platforms (Telegram, Matrix, Email, CLI), executes an agentic tool loop backed by ~40 built-in tools, runs a visual workflow engine with ten trigger types, maintains long-term memory (SQLite FTS5), learns interaction style, generates improvement proposals via a reflection loop, and exposes a React admin dashboard. The stated design center — verified in code — is a **single process, single event loop, one principal user**, with concurrency arriving from overlapping platform messages, scheduler ticks, subagent delegations, and workflow triggers.

The system is genuinely ambitious for its scale: ~41.7k LOC of Python across 26 packages, a React SPA (~15k LOC), 2272 passing tests, and 51 ADRs. The ADR discipline is real and unusually good; most ADRs accurately describe shipped code.

## 2. Component map (as-built)

```
┌──────────────────────────  hestia serve (one asyncio loop)  ──────────────────────────┐
│                                                                                        │
│  Platforms            Orchestrator (turn state machine)         Background             │
│  ┌──────────────┐    ┌──────────────────────────────────┐    ┌───────────────────┐   │
│  │ Telegram     ├───►│ engine.process_turn               │◄───┤ Scheduler (cron)  │   │
│  │ Matrix       │    │  ├ assembly (context build)       │    │ Reflection        │   │
│  │ Email (in)   │    │  ├ execution (tool loop, stream)  │    │ Style learning    │   │
│  │ CLI REPL     │    │  ├ quality (degeneracy breakers)  │    │ Memory maintenance│   │
│  └──────────────┘    │  ├ finalization (persist/notify)  │    │ Error cleanup     │   │
│                      │  └ lock_manager (per-session)     │    └───────────────────┘   │
│                      └──────────────┬───────────────────┘                             │
│                                     │                                                  │
│  Policy                Tools                 Inference          Persistence           │
│  ┌──────────────┐    ┌──────────────┐      ┌──────────────┐   ┌────────────────────┐ │
│  │ CapabilityGate│───►│ ToolRegistry │      │ InferenceClient│ │ SQLite (aiosqlite) │ │
│  │ TrustPresets  │    │ 40+ builtins │      │ + SlotManager  │ │ 16 stores (ADR-040)│ │
│  │ InjectionScan │    │ artifacts    │      │ KV HOT/WARM/COLD│ │ FTS5 memory       │ │
│  └──────────────┘    └──────────────┘      └──────────────┘   └────────────────────┘ │
│                                                                                        │
│  Workflows                              Web dashboard                                 │
│  ┌──────────────────────────────┐      ┌──────────────────────────────┐              │
│  │ TriggerRegistry (event bus)  │      │ FastAPI :8765 (0.0.0.0)      │              │
│  │ WorkflowExecutor (DAG)       │      │ AuthMiddleware + 2FA codes   │              │
│  │ nodes: tool/llm/http/send/…  │      │ React SPA (single 2.7MB chunk)│              │
│  └──────────────────────────────┘      └──────────────────────────────┘              │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Key structural facts:

- **Composition root:** `AppContext` (`src/hestia/app.py:200`) builds all stores eagerly, expensive subsystems lazily via `cached_property`. Clean, testable, single place to understand wiring.
- **Turn pipeline:** `engine.process_turn` → per-session `asyncio.Lock` → assembly → execution (tool loop w/ streaming) → quality classification → finalization. Every transition journaled to `turn_transitions`.
- **Trust boundary:** `CapabilityGate` (ADR-042) consulted from the orchestrator's `_dispatch_tool_call`. **But see §4 — the "every path" claim is false today.**
- **Persistence:** SQLAlchemy Core over aiosqlite; 16 focused stores behind DTOs (ADR-040); runtime migrations additive/idempotent in one transaction; Alembic reference-only.
- **Memory:** FTS5 + BM25, soft-delete + undo + trace for automated maintenance (ADR-049).
- **Frontend:** Vite + React, no router library (state-based page switching), bespoke CSS token system, centralized copy catalog.

## 3. Control/data flows that matter

### 3.1 Chat turn (happy path)
platform poller → allowlist → workflow-response interception → `PlatformRunner.on_message` (identity resolution, ContextVar binding) → session cache/get-or-create → `process_turn` under session lock → context build (prefix layers + tokenize cache + budget math) → streaming LLM call → tool-call parse → gate check → tool execute → result truncate/artifact-promotion/inject-scan → loop (≤ `max_iterations`) → final response streamed+edited on platform → finalize persists turn/messages/trace/slot.

### 3.2 Scheduled task
scheduler tick (60s) → due tasks from store → `is_locked()` probe → set `next_run_at` **before** dispatch → full `process_turn(channel=SCHEDULER)` inline in tick → publish `schedule_fired`.

### 3.3 Workflow trigger
event/webhook/chat-command/schedule_fired → `TriggerRegistry._on_event` (fire-and-forget bus task) → `WorkflowExecutor.execute` (whole DAG, persist only at end) → nodes dispatched through NODE_TYPES registry (**tool_call/investigate bypass the gate** — SEC-001) → `workflow_completed` published.

### 3.4 Web auth
request-code (code delivered over Telegram/Matrix to a **client-supplied recipient** — SEC-002) → verify (10⁶ space, rate-limited, single-use, 256-bit token issued memory-only) → bearer token → AuthMiddleware on `/api/*`.

## 4. Architectural strengths

1. **Process discipline is load-bearing and visible.** ADRs match implementation better than in any comparably-sized solo project this auditor has seen; tests cite ADR/audit IDs; destructive automation is reversible-by-construction (soft delete, undo windows, digests).
2. **The composition root is clean.** One class owns wiring; lazy properties keep startup cheap; deprecation aliases ease migration. `make_orchestrator` is the only factory anyone needs.
3. **State-machine rigor.** Explicit transition table, journaled transitions with collision retry, re-entrancy guard, typed error taxonomy mapped to user-safe sanitization. Crash forensics are genuinely possible.
4. **Token engineering is first-rate.** Server-truth `/tokenize` counting, batched separator trick, prefix caches keyed by content hash, reasoning stripped from history, calibration correction factors. This subsystem would survive contact with any model swap.
5. **Security primitives where applied are textbook**: webhook HMAC (constant-time, replay window, reveal-once secrets), SSRF transport validating every redirect hop, fail-closed presets, confirmation requester-binding, secret scrubbing before audit persistence.
6. **Test architecture**: fakes at true boundaries, real async SQLite, genuine 20-writer race tests, deterministic 260s suite. This is why the bug-finding below could be so specific.

## 5. Architectural weaknesses (summary; details in companion docs)

| # | Weakness | Evidence | Impact |
|---|----------|----------|--------|
| ARCH-001 | **Trust boundary enforced by convention, not chokepoint.** ADR-042 claims every tool path is gated; four paths are not: workflow `tool_call`/`investigate` nodes (SEC-001, verified directly at `executor.py:366-378`, `nodes/tool_call.py:54`), policy-delegation `delegate_task` call (`execution.py:1410`), truncated-write recovery (`quality.py:200`). Dead controls: `workflow.trust_level` never read by executor; `TrustConfig.scheduler_*` flags never passed as gate `allow_list`; gate's own `auto_approved` verdict discarded and re-derived divergently. | `gate.py:90` docstring vs. call-site map in `08_SECURITY_PRIVACY.md` | Critical security gap; false sense of safety |
| ARCH-002 | **Fire-and-forget concurrency without lifecycle.** Bus handlers (`bus.py:49-55` unbounded fan-out), screencast frame tasks (`browser_stream.py:155`), workflow executions, pollers — spawned, never cancelled/tracked/backpressured. `EventBus.publish_nowait` fallback literally destroys its own handler tasks (`bus.py:66-68`). | Multiple | Hung executions, lost events, leaks |
| ARCH-003 | **Per-session serialization has a pop race.** `lock.py:50-51` prunes entries when `locked()` is False — but asyncio locks report unlocked between release and waiter resumption, and `engine.py:320` calls prune synchronously post-release. Two turns can run concurrently on one session, voiding ADR-041 silently. Verified by inspection. | BUG-001 | Critical correctness invariant broken |
| ARCH-004 | **Platform adapters are siblings, not instances of a shared contract.** Reset semantics diverge (LLM summary vs fixed marker), command parsing reimplemented worse on Matrix (`startswith("/reset")` matches `/resetnow`), streaming exists only on Telegram, chunking only on Telegram, edit-rate-limit logic duplicated with different pruning (Matrix's grows unbounded). | platforms audit | Behavior differs per surface; bugs fixed N times |
| ARCH-005 | **Workflow engine has execution semantics but no execution *management*.* No RUNNING state, no cancellation, no duration ceiling, no concurrency guard, no crash record, cron triggers piggybacked on unrelated scheduler events (BUG-005: cron workflows never fire unless some other task fires that minute). | workflows audit | Unbounded loops possible; features appear broken |
| ARCH-006 | **Persistence has three DDL sources and fragmented idioms.** schema.py vs raw-DDL shims in two stores vs Alembic drift; ORM-typed inserts vs pre-formatted `sa.text()` strings (root cause of the tuple-binding crash BUG-007 and PG-incompatible timestamps); timestamp format fragmentation causes wrong same-day comparisons. | persistence audit | PG path broken; subtle scheduling bugs |
| ARCH-007 | **Silent failure as default error strategy.** Interpolation returns `""` for missing keys; skipped workflow nodes emit no NodeResult; invalid LLM decisions return `status=ok` with half the graph gone; stream stall becomes fake `"stop"`; SSE server errors ignored until timeout; frontend discards malformed JSON silently; allowlist mismatches deny silently. Recurring across every layer. | throughout | Users and operators get no signal; debugging cost multiplies |
| ARCH-008 | **Module-global web context singleton** (`set_web_context`) plus monkey-patched `app.inference.close = _noop_close` in serve (`serve.py:34`) — small but real brittleness in lifecycle management. | serve.py, web/context.py | Test contamination; fragile shutdown |

## 6. Challenge-the-architecture assessment

**Decisions still earning their complexity:**
- Turn state machine + journaling (ADR-012): yes — forensics proved their worth in the Aug 13 llama-crash investigation.
- Store split with DTOs (ADR-040): yes, though the split should have come with a shared query helper (the ×4 duplicated WHERE builders produced two copies of the same bug).
- FTS5-not-vectors (ADR-029): correct for single-user scale; revisit only if semantic search complaints materialize.
- Tokenize cache + calibration (ADR-021): emphatically yes.
- Python-file config (ADR-028): acceptable for operator-developer, but it forks behavior between `~/Hestia` and `~/Hestia-runtime` and makes config drift invisible; the env-override layer already covers 80% of what runtime divergence needs.

**Decisions now constraining the project:**
1. **Gate placement.** The gate was bolted onto the orchestrator's dispatch site rather than into the registry. Every new execution surface (workflows got nodes; delegation got a policy fast-path; quality got recovery writes) silently missed it. This is the highest-leverage architectural fix available: move enforcement into `ToolRegistry.call` (or wrap handlers at registration), keep the gate for policy *decisions*, and make the ungated path impossible by construction. See `12_PRIORITY_ROADMAP.md` #1.
2. **Workflow executor as a whole-graph coroutine.** Persist-once-at-end means no observability, no cancellation, no resumability. Given Hestia already has journaled turns, borrowing the same pattern (execution row created upfront, node results appended) is incremental, not a rewrite.
3. **Scheduler as sole cron authority but not used by workflows.** Schedule-trigger workflows should be registered as first-class `scheduled_tasks` (memory maintenance already does exactly this — the pattern exists in-repo).

**Accidental architecture to retire:** dead `session_handoffs` table (46 legacy rows, zero readers); duplicated `get_turn_messages`; three scheduler-callback factories where one suffices; `CliPlatform` used only by its own tests; deprecated `CoreAppContext`/`FeatureAppContext`/`CliAppContext` aliases; `TelegramConfig.fallback_ips` and friends.

## 7. Documented-vs-actual discrepancies

1. **ADR-042 / gate docstring** ("every execution path") vs. reality (four bypasses) — the most consequential discrepancy found anywhere in the repo.
2. **README architecture section** lists `core/`, `orchestrator/`, etc. accurately, but does not mention `commands/` (~3k LOC, the actual home of CLI commands post-ADR-020 decomposition), `identity/`, `diagnostics/`, or `blocked_actions/`.
3. **schema.py comment** claims `get_or_create_session` uses INSERT..ON CONFLICT upsert; implementation is SELECT-then-INSERT with IntegrityError retry (`session_store.py:93-128`). Functionally safe; comment wrong.
4. **Two files claim ADR-051.** `docs/adr/ADR-051-external-tool-modules.md` and `ADR-051-two-tier-topic-scoped-memory.md`.
5. **`trace_store.record_egress` docstring** says "never raises"; only the URL parsing is guarded.
6. **UPGRADE.md / README** say Alembic is "reference only" — accurate — but nothing records which tables were never covered by any revision (most of them; see `02_BACKEND.md` §Migrations).

## 8. Recommendations (architectural)

1. **Make ungated tool invocation impossible by construction** (ARCH-001/SEC-001): registry-level enforcement wrapper; gate stays for decision policy; add regression test asserting `terminal` via a paranoid workflow is denied. Effort: days. Benefit: eliminates an entire class of security bugs permanently.
2. **Fix the serialization primitive** (ARCH-003/BUG-001): never prune a lock with waiters; or replace dict-pop pruning with refcounted acquisition. Small diff, restores ADR-041.
3. **Give workflows an execution row lifecycle** (ARCH-005): create RUNNING row upfront, append node results, sweep stale rows at startup, add duration ceiling + per-workflow mutex. Reuses existing patterns.
4. **Extract a platform-behavior contract** (ARCH-004): command parsing, reset flow, message chunking, edit rate-limit as shared helpers or base-class defaults. Removes the per-surface bug multiplier.
5. **Standardize persistence idioms** (ARCH-006): one query-builder helper, one datetime normalization function, schema.py as single DDL source, delete raw-DDL shims.
6. **Adopt a loud-failure convention** (ARCH-007): interpolation warnings, skipped-node results, structured injection flag instead of string matching. Cheap individually; compounding culturally.

None of these require a rewrite. All are incremental; #1 and #2 are surgical.

## 9. Synthesis pass — common root causes

Reading all subsystem findings together, five root causes generate the majority of the register:

1. **Enforcement by convention instead of chokepoint** (ARCH-001). The CapabilityGate, requester-binding, and audit trail are invoked *by choice* at call sites rather than structurally guaranteed by the registry. Every bypass (SEC-001/003/004), every dead control (`trust_level`, scheduler flags, `auto_approved`), and the workflow engine's whole security posture descend from this single decision.
2. **Fire-and-forget concurrency without lifecycle** (ARCH-002). Event-bus handlers, screencast frame tasks, workflow executions, pollers, and background loops are spawned but never tracked, cancelled, bounded, or backpressured. This one cause produces the infinite self-trigger (BUG-004), unhangable executions (BUG-037), destroyed bus tasks (BUG-029), dropped frames, and the at-most-once cron semantics (BUG-030).
3. **Silent failure as default error strategy** (ARCH-007). Interpolation `""`, skipped nodes invisible, invalid LLM decisions yielding ok, stream stalls becoming fake `"stop"`, swallowed SSE errors, silent allowlist mismatch, silent cron misses, frontend JSON discard. Users and operators receive absence instead of information; nearly every Medium finding in the register has a silent-failure component.
4. **Parallel evolution without contract extraction** (ARCH-004/006). Telegram and Matrix, ORM vs raw-SQL store idioms, four WHERE-builders, two edit-rate-limiters, two reset flows: each duplication has already produced divergent behavior or the same bug twice. The fix pattern is always the same — extract the shared helper, then diverge deliberately.
5. **Process drift at the quality gates** (TEST-001). The repo's own methodology treats pytest/mypy/ruff/web-ui build as blocking; all are currently red or broken. The audit's findings were findable precisely because invariants existed as ADRs and tests — but nothing currently *forces* new code through them.

These five causes explain why the fixes cluster so cleanly: I-1/I-2/I-3 (roadmap) attack causes 5→1→3's worst instance; S-3 attacks cause 2 for workflows; the consistency sweeps attack cause 4.
