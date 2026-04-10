# HESTIA

**Local-First Personal Assistant Framework**
**Design & Build Plan**

*Revised April 2026*
*Reflects actual build through Phase 2b (v0.1.0 + develop)*

Target: RTX 3060 12GB | Qwen 3.5 9B UD Q4_K_XL | llama.cpp
Dylan O'Keefe | dylanokeefedev@gmail.com

---

## 1. Executive Summary

Hestia is a local-first, constrained-hardware agent framework for personal assistants running on a single consumer GPU. It is built specifically for llama.cpp, designed for one user, and opinionated about doing the right thing for small hardware instead of trying to be everything to everyone.

This document is the revised design plan, updated to reflect what was actually built through Phase 2b (196 tests, 14 ADRs, SlotManager and Scheduler shipped). It notes where the implementation diverged from the original plan, why those changes were beneficial, and where decisions may need revisiting.

### 1.1 What Has Shipped

| Component | Status | Notes |
|-----------|--------|-------|
| InferenceClient | Shipped | Phase 1a. Tokenize, chat, slot ops, calibration. |
| SessionStore | Shipped | Phase 1a. SQLAlchemy Core async, archive support. |
| ContextBuilder | Shipped | Phase 1b. Token budgeting, pair integrity, protected regions. |
| ToolRegistry | Shipped | Phase 1b. Meta-tool pattern, @tool decorator, metadata. |
| ArtifactStore | Shipped | Phase 1b. Basic put/get, inline storage. |
| PolicyEngine | Partial | Stub with retry_after_error only. Other hooks not yet needed. |
| Orchestrator | Shipped | Phase 1c. Full 10-state machine, confirmation enforcement. |
| CLI Adapter | Shipped | Phase 1c. Chat, ask, init, health, meta-commands. |
| SlotManager | Shipped | Phase 2a. LRU eviction, HOT/WARM/COLD, leak fix. |
| Scheduler | Shipped | Phase 2b. Cron + one-shot, asyncio loop, CLI commands. |
| Telegram Adapter | Not started | Original Phase 2. Deferred to Phase 3. |
| Subagent Delegation | Not started | States exist in enum. Logic not wired. |
| Long-term Memory | Not started | FTS5 schema not created yet. |
| Matrix Adapter | Not started | Dev/test adapter. Deferred to Phase 4. |

---

## 2. Design Principles

These remain unchanged from the original design. Every one of them came from a concrete bug or performance problem in the Hermes predecessor.

### 2.1 Tokenize, don't estimate

Use llama-server's /tokenize endpoint for context budgeting. The implementation uses a two-number calibration (body_factor + meta_tool_overhead_tokens) measured empirically and recorded in docs/calibration.json (ADR-011).

### 2.2 Work with the chat template, not around it

llama.cpp's --jinja mode plus reasoning_format: deepseek is the clean path for Qwen-class models. Strip historical reasoning from the API payload.

### 2.3 Fail loud

Every error path sends something to the user. The EmptyResponseError guard (Phase 1c) is the direct embodiment of this: if the model returns empty content with finish_reason stop or length, the orchestrator raises rather than silently continuing.

### 2.4 Truncation over summarization

Default compression is rule-based truncation. ContextBuilder drops oldest non-protected messages before the request leaves the process.

### 2.5 Budget is known at build time

The context builder computes the exact token count before calling the model. If the budget is exceeded, compression happens before the request, not after a failed send.

### 2.6 Tools are Python functions

A tool is a function with a docstring, type hints, and an optional metadata block. The registry auto-generates the JSON schema. No YAML, no DSL.

### 2.7 Slots are leased, not owned

Sessions don't own slots across idle periods. SlotManager (Phase 2a) leases slots on acquire() and checkpoints on save(). Eviction is LRU when the pool is full.

### 2.8 Progress is visible

Not yet implemented. Requires platform adapters with edit_message support (Telegram, Matrix). Deferred to Phase 3.

### 2.9 Config is code

*Needs revisiting. See Section 6, Design Debt.*

The original plan called for a typed Python config file. What shipped is Click CLI options and constructor arguments. This works for CLI-only usage but will need consolidation into a proper Config dataclass before Telegram lands.

### 2.10 State is durable

Sessions, turns, transitions, messages, scheduled tasks are all in SQLite. Nothing in-memory-only except the SlotManager's _assignments cache, which reconciles against SessionStore on mismatch.

### 2.11 Large outputs live in durable storage; the model sees handles

ArtifactStore exists and works. The artifact tools (read_artifact, grep_artifact) are registered but not fully exercised in integration tests yet.

### 2.12 Policy is separated from execution

*Partially implemented. See Section 6, Design Debt.*

The PolicyEngine interface exists and the orchestrator delegates retry decisions to it. But delegation, compression, eviction, tool exposure, and reasoning budget policies are either hardcoded or not yet needed. The separation is architecturally clean; the methods just aren't populated yet.

---

## 3. Architecture

Three rings: platforms on the outside, runtime in the middle, persistence on the inside. Every decision that isn't pure execution lives in the policy engine.

### 3.1 Current Directory Layout

The original design put most subsystems under src/hestia/core/. The actual build spread them into top-level packages, which is better for navigation and import clarity:

```
src/hestia/
  cli.py                        # CLI entry point (Click)
  errors.py                     # Shared exception types
  core/                         # Core types + inference client
    inference.py                # llama.cpp HTTP wrapper
    types.py                    # Message, Session, ChatResponse, etc.
  context/                      # Context building
    builder.py                  # Token budgeting, pair integrity
  orchestrator/                 # Turn state machine
    engine.py                   # Orchestrator.process_turn()
    transitions.py              # ALLOWED_TRANSITIONS table
    types.py                    # Turn, TurnState, TurnTransition
  inference/                    # Slot management (policy layer)
    slot_manager.py             # SlotManager with LRU eviction
  scheduler/                    # Background task loop
    engine.py                   # Scheduler with asyncio Event
  tools/                        # Tool system
    registry.py                 # ToolRegistry + meta-tool dispatch
    metadata.py                 # @tool decorator, ToolMetadata
    types.py                    # ToolCallResult, ToolSchema
    builtin/                    # Built-in tools
      current_time.py, read_file.py, terminal.py, read_artifact.py
  artifacts/                    # Artifact storage
    store.py                    # ArtifactStore (put/get)
  persistence/                  # Database layer
    db.py                       # Database connection wrapper
    schema.py                   # SQLAlchemy table definitions
    sessions.py                 # SessionStore (CRUD + slot tracking)
    scheduler.py                # SchedulerStore (task CRUD + cron)
  policy/                       # Policy engine
    engine.py                   # PolicyEngine ABC
    default.py                  # DefaultPolicyEngine
```

### 3.2 Component Summary

Each subsystem is described below with its current state and any drift from the original design.

**InferenceClient.** Thin wrapper around llama-server's HTTP API. Shipped in Phase 1a exactly as designed: tokenize, chat, slot_save/slot_restore/slot_erase, health, count_request. The two-number calibration (body_factor + meta_tool_overhead_tokens) replaced the original single-ratio approach after ADR-009 was superseded by ADR-011.

**ContextBuilder.** Shipped in Phase 1b. The algorithm matches the design (protected top/bottom regions, drop oldest middle messages, real token counts). One addition: the builder takes a new_user_message parameter so the orchestrator can include the current message in the count without double-persisting it. The interface signature is slightly different from the original (takes a Session object plus history list rather than just a session ID), which is cleaner because it avoids a redundant database read inside the builder.

**SessionStore.** Shipped in Phase 1a, extended in Phase 2a. Beyond the original design: archive_session() for /reset, create_session(archive_previous=...) for atomic archive-and-create, assign_slot/release_slot with disk-path tracking, update_saved_path for slot checkpoints. The temperature field (HOT/WARM/COLD) is on the Session dataclass as designed; the state field added an ARCHIVED value beyond the original active/idle/archived.

**ToolRegistry + Meta-Tool Pattern.** Shipped in Phase 1b as designed. The meta-tool pattern (call_tool + list_tools) saves roughly 2900 tokens per request for 20 tools. One implementation detail that changed: max_result_chars and auto_artifact_above were collapsed into a single max_inline_chars parameter (ADR in code, not a numbered ADR). The confirmation enforcement for the call_tool meta-tool path was a Phase 1c bug fix (tools with requires_confirmation=True were bypassed when called via call_tool).

**ArtifactStore.** Shipped in Phase 1b. Basic put/get with file-backed storage. The original design described inline database storage for small artifacts and a TTL/cleanup system. What shipped is simpler: all artifacts go to disk, no TTL yet. The read_artifact tool exists. grep_artifact and list_artifacts are not built yet.

**PolicyEngine.** The interface exists (Phase 1b) but only retry_after_error is populated in DefaultPolicyEngine. The original design described seven policy methods (should_delegate, compression_action, which_to_evict, slot_demotion, visible_tools, reasoning_budget, on_empty_content). These will be filled in as the features they govern are built. The architectural decision to separate policy from execution has already paid off: the orchestrator delegates cleanly to the policy engine without hardcoding retry behavior.

**Orchestrator.** Shipped in Phase 1c. The state machine has all 10 states from the original design. The main divergence: the original design used a handler-per-state dispatch pattern (STATE_HANDLERS dict), while the implementation uses a single process_turn method with a while-loop and inline state handling. At this scale (one orchestrator, 10 states), the inline approach is more readable. If multiple orchestrator variants emerge, the handler pattern would be worth revisiting.

The Turn dataclass is simpler than designed: no status_msg_id (no platform adapters with edit_message yet), no built_messages cache (context is rebuilt each iteration), no reasoning_budget field (passed as a constant). This is appropriate for Phase 2; the missing fields will be added when Telegram lands.

**SlotManager.** Shipped in Phase 2a. Matches the original design's intent (leased slots, HOT/WARM/COLD, LRU eviction) but differs in lifecycle: the original design called for an explicit release() at turn end where the policy engine decides hot/warm/cold demotion. What actually got built keeps sessions HOT after a turn and only demotes on eviction. This is better for the single-user case because the most recently used session is almost always the one that will talk next. The release-and-demote pattern from the design would add unnecessary slot_save/slot_restore churn.

The original design also included a watchdog (max_hold_seconds) to force-release slots held too long. This hasn't been needed because eviction handles the contention case. Worth adding later if stuck tool chains become a problem.

**Scheduler.** Shipped in Phase 2b. The original design specified APScheduler with decorator-based Python function tasks. What got built is much better for the agent use case: tasks are prompts (strings processed by Orchestrator.process_turn), not Python functions. This means users create scheduled tasks dynamically from the CLI without writing code. The dependency changed from apscheduler to croniter (much lighter). The asyncio-loop-with-Event pattern is simpler than APScheduler's job store machinery.

Missing from the design that didn't ship: reactive notifications (only notify if result changed), task decorator pattern, scheduled tasks as Python functions. The prompt-based approach is the right call for an LLM agent framework; reactive mode can be layered on top later.

---

## 4. Intentional Divergences from Original Design

These are deliberate changes made during implementation that improved the design.

### 4.1 Phasing

The original roadmap had five phases over three weeks. The actual build restructured into tighter cycles:

| Phase | Original Plan | What Actually Happened |
|-------|--------------|----------------------|
| 1a | Part of Phase 1 (Days 1-3) | Inference + Persistence + Calibration |
| 1b | Part of Phase 1 (Days 1-3) | Tools + Context + Artifacts |
| 1c | Part of Phase 1 (Days 1-3) | Orchestrator + CLI + State Machine |
| 2a | Phase 2: Telegram + SlotManager | SlotManager only (no Telegram) |
| 2b | Phase 4: Scheduler + Memory | Scheduler only (no Memory) |

The key change: each cycle is one focused subsystem with full tests, ADR, and handoff report, reviewed before the next cycle starts. This is slower per-feature but catches bugs much earlier. The Phase 1c confirmation bypass bug (tools with requires_confirmation=True were silently allowed through the meta-tool path) was caught in review and fixed before it could become a production issue.

### 4.2 Scheduler: Prompts Instead of Python Functions

The original design had scheduled tasks as decorated Python functions. The implementation uses prompt strings processed by the orchestrator. This is the right choice for an LLM agent framework: the whole point is that the agent processes natural language, so scheduled tasks should be natural language too. A user can type `hestia schedule add --cron "0 9 * * 1-5" "Summarize my unread Matrix messages"` without writing any code.

### 4.3 SlotManager: No Post-Turn Release

The original design had the policy engine decide hot/warm/cold demotion after every turn via release(). The implementation keeps sessions HOT and only demotes on eviction. For a single-user system with 4 slots, the most recent session is almost always the one that will be used next. Forcing a save-to-disk and restore-from-disk cycle on every turn would add 400ms of latency for no benefit. Eviction handles the rare case where all 4 slots are needed by different sessions.

### 4.4 Directory Layout: Flat Packages Instead of core/

The original design put most subsystems under src/hestia/core/. The actual build created top-level packages: orchestrator/, inference/, scheduler/, context/, policy/, persistence/. This is better for navigation (every import starts with hestia.<subsystem>) and avoids a god-module core/ that grows without bound.

### 4.5 Dependencies: croniter Instead of APScheduler

APScheduler is a full job scheduling framework with its own execution model, job stores, and executors. Hestia's scheduler is a simple asyncio loop that queries the database for due tasks. croniter (a single-purpose cron expression parser) is all it needs. The runtime deps are now: httpx, sqlalchemy, aiosqlite, asyncpg, click, croniter, pydantic, python-dateutil, alembic. No APScheduler, no langchain, no transformers, no torch.

### 4.6 Orchestrator: Inline State Handling Instead of Handler Dispatch

The original design used STATE_HANDLERS[turn.state] dispatch. The implementation handles states inline in a while-loop inside process_turn(). At this scale, inline is more readable and debuggable. The handler pattern would be worth revisiting if multiple orchestrator variants emerge (e.g., a streaming orchestrator, a batch orchestrator).

---

## 5. Test Coverage and Quality

| Phase | Tests | Delta | Key Additions |
|-------|-------|-------|---------------|
| 1a | 42 | +42 | Inference, persistence, calibration |
| 1b | 96 | +54 | Tools, context builder, artifacts, registry |
| 1c | 123 | +27 | Orchestrator, state machine, CLI, integration |
| 2a | 142 | +19 | SlotManager unit + integration, session slots |
| 2b | 196 | +54 | SchedulerStore, Scheduler engine, CLI schedule |

Quality tooling: **pytest** for testing, **ruff** for linting, **mypy** for type checking. All three run on every phase. mypy has 16 errors at Phase 2b (mostly croniter untyped stubs and annotation gaps), ruff is clean on src/ and tests/.

Architecture Decision Records: 14 ADRs in docs/DECISIONS.md covering naming, tooling, persistence, calibration, state machine design, slot management, and scheduler design. ADR-009 was superseded by ADR-011 when the single-ratio calibration proved too imprecise.

---

## 6. Design Debt and Items to Revisit

These are areas where the current implementation is known to be incomplete or suboptimal.

### 6.1 Config Is Not Code Yet

The original principle (2.9) called for a typed Python config file. What exists is Click CLI options and constructor arguments scattered across cli.py. Before Telegram ships, Hestia needs a proper Config dataclass that consolidates inference URL, model name, slot pool size, database path, artifact path, system prompt, and platform configs into one importable object. This is a Phase 2c prerequisite.

### 6.2 PolicyEngine Is Mostly Stub

Only retry_after_error is implemented. The should_delegate, compression_action, visible_tools, and reasoning_budget methods need to be filled in as features demand them. The separation is architecturally clean; the methods just aren't populated. This becomes urgent when subagent delegation or multi-platform tool exposure ships.

### 6.3 No Alembic Migrations

Schema changes have been handled by create_tables() which is fine for development but won't work for production upgrades. Before v1.0, Alembic needs to be set up with an initial migration and a migration per schema change.

### 6.4 No Crash Recovery

The original design described resuming in-flight turns on startup. Currently, a crash mid-turn leaves the turn in a non-terminal state with no recovery. For a single-user CLI tool, this is acceptable (the user just re-sends). For a Telegram bot running as a systemd service, it needs fixing.

### 6.5 Artifact Tools Not Exercised

read_artifact exists as a registered tool. grep_artifact and list_artifacts are described in the design but not built. The ArtifactStore has no TTL or cleanup. These become important when subagent delegation ships (subagent transcripts are artifacts).

### 6.6 SchedulerStore Missing enable_task and delete_task

Phase 2b shipped with disable_task but no way to re-enable a task, and schedule remove actually just disables rather than deleting. The CLI schedule enable command is a non-functional stub. These are 5-10 line fixes folded into the Phase 2c cleanup.

### 6.7 Progress Visibility Not Implemented

Design principle 2.8 (progress is visible) requires platform adapters with edit_message support. The Turn dataclass has no status_msg_id field yet. This ships with Telegram.

### 6.8 Missing Built-in Tools

The design specified 10 built-in tools. Four shipped: current_time, read_file, terminal, read_artifact. Still missing: write_file, list_dir, http_get, search_memory, save_memory, delegate_task, schedule_task. Some of these (search_memory, save_memory, delegate_task) depend on unbuilt subsystems.

---

## 7. Remaining Roadmap

The original five-phase, three-week roadmap is replaced with the following, organized by dependency order. Each phase is scoped for a single Kimi build cycle (roughly 1-2 hours) followed by Claude review.

### Phase 2c: Cleanup + Platform Adapter Base

Prerequisite for Telegram. Consolidates scattered config, establishes the Platform adapter interface, and fixes Phase 2b stubs.

- **Section 0 Cleanup:** Add SchedulerStore.set_enabled() and delete_task(). Fix CLI schedule enable stub and schedule remove. Fix _fire_task string comparison (use SessionState.ACTIVE enum instead of hardcoded "active").
- **Config dataclass:** Consolidate CLI options into a typed HestiaConfig with InferenceConfig, SlotConfig, SchedulerConfig, and PlatformConfig sub-objects. CLI reads from config file with CLI overrides.
- **Platform ABC:** Abstract base class with start(), send_message(), edit_message(), send_status(), send_error(). CLI adapter refactored to implement this interface.
- **Built-in tools:** Add write_file, list_dir, http_get (the ones that don't depend on unbuilt subsystems).
- **Alembic setup:** Initial migration from current schema. Migration workflow documented.

### Phase 3: Telegram Adapter

The primary user-facing transport. This is how you actually talk to the bot in production.

- **TelegramAdapter** implementing Platform ABC. HTTP/1.1 forcing via httpx (learned from Hermes). Fallback IPs for DNS flakiness. Rate-limited edit_message (max 1/1.5s per message).
- **Status message editing:** Turn gets a status_msg_id field. Orchestrator updates status during state transitions (Thinking... / Running terminal... / Done).
- **Systemd service files:** hestia-llama.service (llama-server) and hestia-agent.service (Hestia process). Install script.
- **Crash recovery:** On startup, scan for turns in non-terminal states. If the slot can be restored, resume. Otherwise, mark FAILED and notify user.
- **Scheduler delivery to Telegram:** Scheduler response_callback routes to the originating platform/user.

### Phase 4: Long-Term Memory + Matrix Dev Adapter

- **FTS5 memory store:** search_memory(query) and save_memory(content, tags) tools. SQLite FTS5 virtual table. No vector DB, no embeddings.
- **MatrixAdapter:** Dev/test transport. matrix-nio async client. Room-per-session. Valuable because Kimi and other CLI tools can drive a Matrix client for closed-loop automated testing.
- **Integration test harness:** Drive the agent via Matrix CLI, verify end-to-end tool chains, scheduled task firing, and multi-turn conversations.

### Phase 5: Subagent Delegation

The biggest remaining subsystem. Same concept as the Hermes design, but built on the existing orchestrator.

- **delegate_task tool:** Spawns a Turn in a new session with its own slot. Subagent runs until completion or timeout.
- **SubagentResult envelope:** Structured return (summary, status, completeness, artifact_refs, follow_up_questions, next_actions, error, duration, tool_calls_made). The main session's context grows by roughly 300 tokens per delegation regardless of subagent work volume.
- **AWAITING_SUBAGENT and AWAITING_USER states:** Wire up the transitions that already exist in the state enum. Subagent can ask questions routed to the user via the active platform.
- **PolicyEngine.should_delegate():** Implement delegation policy based on tool chain length, projected result sizes, and explicit user requests.

### Phase 6: Polish, Docs, Share

The agent is fully functional at this point. This phase is about making it presentable and installable by others.

- **Documentation:** Getting started guide, hardware profiles (8GB / 12GB / 24GB / CPU-only), writing custom tools, policy customization.
- **Example configs and tools:** Weather monitor (ported from Hermes), RSS digest, home assistant bridge.
- **README:** Clear positioning for who this is for and who it isn't for.
- **CLI observability commands:** hestia status, hestia logs, hestia sessions, hestia policy log, hestia turn <id>, hestia artifact <id>.
- **Webhook adapter:** Generic HTTP POST adapter for Home Assistant, cron callers, custom UIs.
- **Video walkthrough:** From zero to Telegram bot in 30 minutes on a 3060.
- **Distribution:** GitHub, r/LocalLLaMA post, optional Hacker News when v1.0 ships.

---

## 8. Hardware-Specific Optimizations

These are what earn Hestia its "built for 12GB" claim. All are implemented or directly supported by the architecture.

- **Accurate token budgeting** via /tokenize endpoint. Two-number calibration (body_factor + meta_tool_overhead_tokens). Takes roughly 5ms per count. Implemented and tested.
- **TurboQuant KV cache** (--cache-type-k turbo3 --cache-type-v turbo3). Roughly 5x KV cache compression. For a 16K context, that's roughly 2.4 GB saved per slot. Documented in example service file.
- **Flash attention** always on (--flash-attn on).
- **Meta-tool pattern** saves roughly 2900 tokens per request for 20 tools. Implemented and measured.
- **Reasoning budget tuning:** Currently a fixed 2048 default. The PolicyEngine.reasoning_budget() hook exists for future per-task tuning (512 for quick, 2048 for standard, 4096 for heavy synthesis).
- **Slot save/restore to NVMe.** A 16K slot with TurboQuant is roughly 50 MB on disk. Restore takes roughly 200ms. SlotManager handles this transparently.
- **Reasoning strip on history.** ContextBuilder strips reasoning_content from all historical assistant messages before the API call.
- **Tool result caps at build time.** max_inline_chars applied before counting, not after. Full results go to ArtifactStore; capped version goes to the model.
- **Truncation-first compression.** Drop oldest non-protected turns. No summarization in the hot path. Summarization is future opt-in with hard timeout.

---

## 9. Decisions Locked In

These are settled and recorded in ADRs. They won't change without a new ADR superseding them.

- **Name:** Hestia. Goddess of the hearth, home, and domestic life. (ADR-001)
- **Package manager:** uv. Lockfile-by-default, fast installs. (ADR-002)
- **Language:** Python 3.11+. (ADR-003)
- **Database:** SQLite by default, Postgres via URL override. SQLAlchemy Core async. (ADR-004)
- **Subagents:** Same process, different slot, different asyncio task. (ADR-005)
- **Search:** FTS5-only for v1. Vector search is a future plugin. (ADR-006)
- **No web UI in v1.** Read-only dashboard is a possibility later. (ADR-007)
- **License:** Apache 2.0. (ADR-008)
- **Calibration:** Two-number (body_factor + meta_tool_overhead_tokens). (ADR-011)
- **Turn state machine:** 10 states, ALLOWED_TRANSITIONS table, platform-agnostic confirmation callback. (ADR-012)
- **SlotManager:** Owns KV-cache lifecycle, LRU eviction, SessionStore is source of truth. (ADR-013)
- **Scheduler:** Runs tasks via existing Orchestrator, prompt-based not function-based, croniter for cron parsing. (ADR-014)

---

## 10. Dependencies

Minimal by design. No langchain, no transformers, no torch, no vector DB.

**Runtime:**
httpx, sqlalchemy[asyncio], aiosqlite, asyncpg, click, croniter, pydantic, python-dateutil, alembic.

**Development:**
pytest + pytest-asyncio, ruff, mypy.

**Future (not yet added):**
python-telegram-bot (Phase 3), matrix-nio (Phase 4).
