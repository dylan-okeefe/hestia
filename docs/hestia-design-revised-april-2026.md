# HESTIA

**Local-First Personal Assistant Framework**
**Design & Build Plan**

*Revised April 2026*
*Reflects actual build through Phase 6 (311 tests, 20 ADRs, develop branch)*

Target: RTX 3060 12 GB | Qwen 3.5 9B UD Q4_K_XL | llama.cpp
Dylan O'Keefe | dylanokeefedev@gmail.com

---

## 1. Executive summary

Hestia is a local-first, constrained-hardware agent framework for personal
assistants running on a single consumer GPU. It is built specifically for
llama.cpp, designed for one user, and opinionated about doing the right thing
for small hardware instead of trying to be everything to everyone.

This document is the design plan, updated to reflect what was actually built
through Phase 6. It notes where the implementation diverged from the original
plan, why those changes were beneficial, and what remains.

### 1.1 What has shipped

| Component | Phase | Status | Notes |
|-----------|-------|--------|-------|
| InferenceClient | 1a | Shipped | Tokenize, chat, slot ops, calibration |
| SessionStore | 1a | Shipped | SQLAlchemy Core async, archive, slot tracking |
| ContextBuilder | 1b | Shipped | Token budgeting, pair integrity, protected regions |
| ToolRegistry | 1b | Shipped | Meta-tool pattern, `@tool` decorator |
| ArtifactStore | 1b | Shipped | File-backed put/get |
| PolicyEngine | 1b + 6 | Shipped | `retry_after_error`, `filter_tools`, `should_delegate` |
| Orchestrator | 1c | Shipped | Full 10-state machine, confirmation enforcement |
| CLI Adapter | 1c | Shipped | chat, ask, init, health, meta-commands |
| SlotManager | 2a | Shipped | LRU eviction, HOT/WARM/COLD, save/restore |
| Scheduler | 2b | Shipped | Cron + one-shot, asyncio loop, CLI commands |
| HestiaConfig | 2c | Shipped | Typed Python config with CLI overrides |
| Platform ABC | 2c | Shipped | Base class, CLI adapter refactored to implement it |
| Alembic migrations | 2c | Shipped | Initial + per-phase migrations |
| Telegram Adapter | 3 | Shipped | HTTP/1.1, rate-limited edits, user allowlist, crash recovery |
| Long-term Memory | 4 | Shipped | FTS5 MemoryStore, `search_memory`/`save_memory`/`list_memories` tools |
| Subagent Delegation | 5 | Shipped | `delegate_task`, SubagentResult envelope, AWAITING_SUBAGENT state |
| Capability Labels | 6 | Shipped | Tool capabilities, `filter_tools` on PolicyEngine |
| Path Sandboxing | 6 | Shipped | `allowed_roots` enforcement on read_file/write_file |
| Failure Tracking | 6 | Shipped | FailureClass enum, FailureStore, CLI `failures` command |
| CLI Observability | 6 | Shipped | `version`, `status`, `failures list/summary` |
| Matrix Adapter | 7 | In progress | Design complete, implementation next |

---

## 2. Design principles

Every one of these came from a concrete bug or performance problem in the
Hermes predecessor.

### 2.1 Tokenize, don't estimate

Use llama-server's `/tokenize` endpoint for context budgeting. Two-number
calibration (body_factor + meta_tool_overhead_tokens) measured empirically.

### 2.2 Work with the chat template, not around it

llama.cpp's `--jinja` mode plus `reasoning_format: deepseek` is the clean path
for Qwen-class models. Strip historical reasoning from the API payload.

### 2.3 Fail loud

Every error path sends something to the user. The `EmptyResponseError` guard
catches empty model responses. Failure bundles persist for postmortem.

### 2.4 Truncation over summarization

Default compression is rule-based truncation. ContextBuilder drops oldest
non-protected messages before the request leaves the process.

### 2.5 Budget is known at build time

The context builder computes the exact token count before calling the model.
Compression happens before the request, not after a failed send.

### 2.6 Tools are Python functions

A tool is a function with type hints and an optional metadata block. The
registry auto-generates the JSON schema. No YAML, no DSL.

### 2.7 Slots are leased, not owned

Sessions don't own slots across idle periods. SlotManager leases slots on
`acquire()` and checkpoints on `save()`. Eviction is LRU when the pool is full.

### 2.8 Progress is visible

Telegram adapter implements `edit_message` for live status updates during turns.
Matrix adapter will follow the same pattern.

### 2.9 Config is code

`HestiaConfig` is a typed Python dataclass loaded from a Python file via
`importlib`. Sub-configs for inference, slots, scheduler, storage, and Telegram.
CLI options override config file values. IDE autocompletion works.

### 2.10 State is durable

Sessions, turns, transitions, messages, scheduled tasks, failure bundles, and
memories are all in SQLite. Nothing in-memory-only except the SlotManager's
`_assignments` cache, which reconciles against SessionStore on mismatch.

### 2.11 Large outputs live in durable storage; the model sees handles

ArtifactStore stores large tool outputs. The model receives a capped inline
version with an artifact reference.

### 2.12 Policy is separated from execution

PolicyEngine interface with `retry_after_error`, `filter_tools`, and
`should_delegate`. The orchestrator delegates decisions without hardcoding.
Capability-based tool filtering restricts subagent and scheduler sessions.

---

## 3. Architecture

Three rings: platforms on the outside, runtime in the middle, persistence on
the inside. Every decision that isn't pure execution lives in the policy engine.

### 3.1 Directory layout

```
src/hestia/
  cli.py                        # Click CLI entry point
  config.py                     # HestiaConfig + sub-configs
  errors.py                     # Exception types + FailureClass
  logging_config.py             # Centralized logging setup
  core/
    inference.py                # llama.cpp HTTP client
    types.py                    # Message, Session, ChatResponse, etc.
  context/
    builder.py                  # Token budgeting, pair integrity
  orchestrator/
    engine.py                   # 10-state turn machine
    transitions.py              # ALLOWED_TRANSITIONS table
    types.py                    # Turn, TurnState, TurnTransition
  inference/
    slot_manager.py             # KV-cache slot lifecycle
  scheduler/
    engine.py                   # Cron + one-shot loop
  tools/
    registry.py                 # ToolRegistry + meta-tool dispatch
    metadata.py                 # @tool decorator, ToolMetadata
    capabilities.py             # Capability label constants
    types.py                    # ToolCallResult, ToolSchema
    builtin/
      current_time.py, read_file.py, write_file.py, list_dir.py,
      http_get.py, terminal.py, read_artifact.py, path_utils.py
  memory/
    store.py                    # MemoryStore (FTS5)
  artifacts/
    store.py                    # File-backed artifact storage
  persistence/
    db.py                       # Database connection wrapper
    schema.py                   # SQLAlchemy table definitions
    sessions.py                 # SessionStore (CRUD + slots + stats)
    scheduler.py                # SchedulerStore (tasks + cron + stats)
    failure_store.py            # FailureStore (bundles)
  platforms/
    base.py                     # Platform ABC
    cli_adapter.py              # CLI adapter
    telegram_adapter.py         # Telegram adapter
  policy/
    engine.py                   # PolicyEngine ABC
    default.py                  # DefaultPolicyEngine
```

### 3.2 Component details

**InferenceClient.** Thin HTTP wrapper for llama-server: tokenize, chat,
slot_save/slot_restore/slot_erase, health. Two-number calibration
(body_factor + meta_tool_overhead_tokens) replaced the original single-ratio
approach (ADR-009 superseded by ADR-011).

**ContextBuilder.** Builds the API request with real token counts. Protected
top/bottom regions, oldest-first middle message dropping, pair integrity for
user/assistant pairs. Takes a Session object plus history list rather than a
session ID, avoiding a redundant database read.

**SessionStore.** Sessions with HOT/WARM/COLD temperature states,
archive/create-and-archive, slot assignment/release, disk-path tracking,
and query methods for status reporting (`count_sessions_by_state`,
`turn_stats_since`).

**ToolRegistry + Meta-Tool Pattern.** The meta-tool pattern (`call_tool` +
`list_tools`) saves ~2,900 tokens per request for 20 tools by not inlining
every tool schema into the API call. Confirmation enforcement works on both
the meta-tool and direct dispatch paths.

**ArtifactStore.** File-backed put/get. Large tool outputs go to disk; the
model sees a capped inline version with an artifact handle.

**PolicyEngine.** `retry_after_error()` for retry decisions,
`filter_tools()` for capability-based tool filtering by session type,
`should_delegate()` for delegation heuristics. Subagent sessions lose
`shell_exec` and `write_local`; scheduler turns lose `shell_exec`.

**Orchestrator.** 10-state turn machine with inline state handling in a
while-loop inside `process_turn()`. Confirmation and response delivery via
injected callbacks. Tool chain tracking feeds FailureStore on turn failure.

**SlotManager.** LRU eviction over a fixed slot pool. Sessions stay HOT after a
turn (no post-turn demotion) because the single-user case almost always reuses
the same session. Disk save/restore for WARM sessions (~200ms on NVMe).

**Scheduler.** Asyncio loop with configurable tick interval. Tasks are prompts
(not Python functions) fired through the same Orchestrator as interactive turns.
Cron expressions via croniter; one-shot tasks auto-disable after firing.
Response delivery via injected callback (stdout for CLI daemon, platform adapter
for Telegram/Matrix).

**MemoryStore.** SQLite FTS5 virtual table with BM25 ranking. No embeddings,
no external services. Factory-pattern tools (`make_search_memory_tool`, etc.)
bound to a store instance. Session ID threading via `contextvars` for memory
attribution.

**Telegram Adapter.** HTTP/1.1 forced via httpx. Rate-limited `edit_message`
(max 1 per 1.5s). User allowlist. Crash recovery scans for stale turns on
startup. Scheduler delivery routes to originating platform/user.

**Subagent Delegation.** `delegate_task` tool spawns a Turn in a new session
with its own slot. SubagentResult envelope caps parent context growth at ~300
tokens regardless of subagent work volume. `AWAITING_SUBAGENT` state in the
turn machine. Timeout via `asyncio.wait_for()`.

**Failure Tracking.** `FailureClass` enum with `classify_error()` mapping from
exception types. `FailureStore` persists bundles with session, turn, class,
severity, message, and tool chain JSON. CLI `failures list` and
`failures summary` for operational visibility.

---

## 4. Intentional divergences from original design

### 4.1 Phasing

The original five-phase roadmap was restructured into tighter cycles. Each
cycle is one focused subsystem with full tests, ADR, and handoff report,
reviewed before the next cycle starts.

| Phase | Original plan | What actually happened |
|-------|--------------|----------------------|
| 1a–1c | Phase 1 (Days 1–3) | Split into three sub-phases: inference+persistence, tools+context, orchestrator+CLI |
| 2a | Phase 2: Telegram + SlotManager | SlotManager only |
| 2b | Phase 4: Scheduler + Memory | Scheduler only |
| 2c | — | Config consolidation + Platform ABC + Alembic + cleanup |
| 3 | Phase 2: Telegram | Telegram adapter + crash recovery |
| 4 | Phase 4: Memory | FTS5 MemoryStore + memory tools |
| 5 | Phase 3: Subagent | Delegation + SubagentResult + policy |
| 6 | Phase 5: Polish | Capability labels + path sandbox + failure tracking + CLI obs |
| 7 | — | Matrix adapter (in progress) |

### 4.2 Scheduler: prompts instead of Python functions

The original design had scheduled tasks as decorated Python functions. The
implementation uses prompt strings processed by the orchestrator. Users create
scheduled tasks dynamically from the CLI without writing code:
`hestia schedule add --cron "0 9 * * 1-5" "Summarize my Matrix messages"`.

### 4.3 SlotManager: no post-turn release

The original design had the policy engine decide HOT/WARM/COLD demotion after
every turn. The implementation keeps sessions HOT and only demotes on eviction.
For a single-user system, the most recent session is almost always next. Forcing
save+restore on every turn would add ~400ms for no benefit.

### 4.4 Flat packages instead of core/

The original design put most subsystems under `src/hestia/core/`. The actual
build created top-level packages: `orchestrator/`, `inference/`, `scheduler/`,
etc. Every import starts with `hestia.<subsystem>`, which is clearer.

### 4.5 croniter instead of APScheduler

APScheduler is a full job scheduling framework with its own execution model.
Hestia's scheduler is a simple asyncio loop querying the database. croniter
(a single-purpose cron parser) is all it needs.

### 4.6 Inline state handling instead of handler dispatch

The original design used `STATE_HANDLERS[turn.state]` dispatch. The
implementation handles states inline in a while-loop. At this scale, inline is
more readable. The handler pattern is worth revisiting if multiple orchestrator
variants emerge.

---

## 5. Test coverage

| Phase | Tests | Delta | Key additions |
|-------|-------|-------|---------------|
| 1a | 42 | +42 | Inference, persistence, calibration |
| 1b | 96 | +54 | Tools, context builder, artifacts, registry |
| 1c | 123 | +27 | Orchestrator, state machine, CLI, integration |
| 2a | 142 | +19 | SlotManager unit + integration |
| 2b | 196 | +54 | SchedulerStore, Scheduler engine, CLI schedule |
| 2c | ~210 | ~+14 | Config, Platform ABC, Alembic |
| 3 | ~230 | ~+20 | Telegram adapter, crash recovery |
| 4 | ~250 | ~+20 | MemoryStore, memory tools, CLI memory |
| 5 | ~280 | ~+30 | Delegation, SubagentResult, policy |
| 6 | 311 | ~+31 | Capabilities, sandboxing, failure store, CLI obs |

Quality tooling: **pytest** for testing, **ruff** for linting, **mypy** for
type checking. All three run on every phase.

Architecture Decision Records: 20 ADRs in `docs/DECISIONS.md`.

---

## 6. Design debt and items to revisit

### 6.1 Artifact tools not fully exercised

`read_artifact` exists. `grep_artifact` and `list_artifacts` are described
in the design but not built. The ArtifactStore has no TTL or cleanup.

### 6.2 Crash recovery scope

Telegram adapter recovers stale turns on startup. The CLI adapter does not.
For a single-user CLI tool, this is acceptable; for production daemon modes
it should be extended.

### 6.3 Progress visibility on CLI

Telegram has live status edits. CLI shows nothing during long turns. A spinner
or streaming output would improve the experience.

### 6.4 Confirmation UX on Telegram

Destructive tools currently fail closed on Telegram (no inline keyboard).
Inline confirmation buttons are tracked as a product gap.

### 6.5 Policy delegation UX

When the policy engine replaces a batch of tool calls with one `delegate_task`,
the duplicate text for multiple `tool_call_id`s (except the first) is
suboptimal. Needs model-facing tool result shaping.

### 6.6 aiosqlite thread warnings

Two `PytestUnhandledThreadExceptionWarning` from aiosqlite on closed event
loops. Housekeeping, not a functional issue.

---

## 7. Remaining roadmap

### Phase 7: Matrix adapter (in progress)

Branch for Matrix work: `feature/phase-7-matrix`. Design: [`docs/design/matrix-integration.md`](design/matrix-integration.md). **Phase 7 cleanup** precedes Matrix — see [`docs/development-process/design-artifacts/kimi-hestia-phase-7-cleanup.md`](../development-process/design-artifacts/kimi-hestia-phase-7-cleanup.md).

- `MatrixAdapter` implementing Platform ABC with `matrix-nio`
- `MatrixConfig` dataclass mirroring TelegramConfig
- `hestia matrix` CLI command
- Room-per-session model with allowlist
- Unit + component tests; E2E tests as optional CI job
- ADR-021

### Post-Phase 7

See [`docs/roadmap/future-systems-deferred-roadmap.md`](roadmap/future-systems-deferred-roadmap.md)
for the full deferred roadmap, organized into tiers:

- **Tier A** — Product gaps: Telegram confirmation UI, artifact tools,
  extended CLI observability, webhook adapter, example configs
- **Tier B** — Future foundations: trace store, failure bundle enrichment,
  artifact trust labels, security findings store
- **Tier C** — Knowledge architecture: five-store model, knowledge router,
  memory epochs, skill lifecycle
- **Tier D** — Skill miner, failure analyst, bounded auto-healing
- **Tier E** — Security loop and adversarial evaluation
- **Tier F** — Policy synthesis

---

## 8. Hardware-specific optimizations

These are what earn Hestia its "built for 12 GB" claim:

- **Accurate token budgeting** via `/tokenize`. Two-number calibration takes
  ~5ms per count.
- **KV-cache quantization** (`--cache-type-k turbo3 --cache-type-v turbo3`).
  ~4x KV-cache compression.
- **Flash attention** always on (`--flash-attn`).
- **Meta-tool pattern** saves ~2,900 tokens per request.
- **Slot save/restore to NVMe.** A 16K slot is ~50 MB on disk. Restore takes
  ~200ms.
- **Reasoning strip.** Historical `reasoning_content` stripped before the API
  call.
- **Tool result caps at build time.** Full results go to ArtifactStore; capped
  version goes to the model.
- **Truncation-first compression.** Drop oldest non-protected turns. No
  summarization in the hot path.

---

## 9. Decisions locked in

Settled and recorded in ADRs. They won't change without a new ADR superseding them.

| ADR | Decision |
|-----|----------|
| 001 | Name: Hestia |
| 002 | Package manager: uv |
| 003 | Language: Python 3.11+ |
| 004 | Database: SQLite default, Postgres via URL; SQLAlchemy Core async |
| 005 | Subagents: same process, different slot, different asyncio task |
| 006 | Search: FTS5-only for v1 |
| 007 | No web UI in v1 |
| 008 | License: Apache 2.0 |
| 011 | Calibration: two-number (body_factor + meta_tool_overhead) |
| 012 | Turn state machine: 10 states, platform-agnostic callbacks |
| 013 | SlotManager: LRU eviction, SessionStore as truth |
| 014 | Scheduler: prompt-based tasks via Orchestrator, croniter |
| 015 | HestiaConfig: typed Python dataclass from Python file |
| 016 | Telegram: HTTP/1.1, rate-limited edits, user allowlist |
| 017 | Memory: SQLite FTS5, no vector search in v1 |
| 018 | Delegation: same-process, SubagentResult envelope |
| 019 | Capability labels + session-aware tool filtering |
| 020 | Typed failure bundles with FailureStore |

---

## 10. Dependencies

Minimal by design. No LangChain, no transformers, no torch, no vector DB.

**Runtime:**
httpx, sqlalchemy[asyncio], aiosqlite, asyncpg, click, croniter, pydantic,
python-dateutil, alembic, python-telegram-bot.

**Development:**
pytest + pytest-asyncio, ruff, mypy.

**Future (Phase 7):**
matrix-nio.
