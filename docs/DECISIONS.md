# Architectural Decisions

This log records architectural decisions made for Hestia. Entries are append-only;
when a decision is superseded, add a new entry referencing the old one rather than
editing history.

## ADR-001: Project name is "Hestia"

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Needed a project name for the local-first agent framework. Too many
  agent frameworks use male names from mythology (Hermes, Odin, Loki, Prometheus).
- **Decision:** Named the project Hestia, Greek goddess of the hearth and home, to
  signal the local-first, personal, domestic nature of the framework and to add a
  non-male name to the space.
- **Consequences:** Project directory, package name, and CLI command are all `hestia`.

## ADR-002: Package manager is `uv`

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Python packaging is notoriously painful. Poetry is slow, pip lacks
  lockfiles by default, and conda is overkill for a single-package project. We
  need fast installs, lockfile-by-default, and a good dev loop.
- **Decision:** Use `uv` (Astral's Python packaging tool) for dependency management,
  virtual environment creation, and build orchestration.
- **Consequences:** Contributors need `uv` installed. Build is faster and more
  reproducible than pip-based workflows.

## ADR-003: Language is Python 3.11+

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Python 3.11 brings significant performance improvements (10-60% faster
  than 3.10), better error messages, and native `asyncio.TaskGroup`. We don't need
  to support older versions because this is a greenfield project targeting modern
  hardware.
- **Decision:** Minimum supported Python version is 3.11. Development happens on
  3.13 when available.
- **Consequences:** Cannot run on Ubuntu 22.04's default Python 3.10 without
  installing a newer version. Use of `|` union syntax and other 3.10+ features
  is allowed.

## ADR-004: Persistence is SQLAlchemy Core async with SQLite default, Postgres via URL override

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** We need durable state (sessions, messages, turns) that survives
  restarts. SQLite is perfect for single-node deployment (zero config, single file).
  However, we may want to run the database on a different machine from the agent
  host in future (e.g., for backup or multi-agent scenarios).
- **Decision:** Use SQLAlchemy Core (not ORM) with async drivers. Default to
  `sqlite+aiosqlite://`, but allow `postgresql+asyncpg://` via config URL change.
  Artifact bytes always stay on the agent host's disk regardless of DB backend.
- **Consequences:** Must write explicit SQL queries, no lazy loading. Schema
  migrations via Alembic. If using remote Postgres, large file reads/writes must
  go through the artifact store, not the DB connection.

## ADR-005: Subagents run in the same process

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Subagent delegation needs isolation but IPC (multiprocessing, gRPC,
  etc.) adds significant complexity for v1. One process is simpler to operate and
  debug. A supervisor can resurrect failed subagents by catching exceptions.
- **Decision:** Subagents are asyncio tasks within the same process, supervised
  by the orchestrator. Different slot, different session, but same Python process.
  Multi-process is deferred to post-v1 if needed.
- **Consequences:** A crashing subagent could crash the whole agent if not caught.
  GIL contention is not an issue because the workload is I/O bound (inference
  calls). Memory is shared, so subagents must not mutate global state.

## ADR-006: Search is FTS-only at first

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Long-term memory needs search. Vector DBs (Chroma, Weaviate, pgvector)
  add deployment complexity and GPU memory pressure. For a personal assistant,
  full-text search is often sufficient.
- **Decision:** SQLite FTS5 is the only search in v1. If vector search is needed
  later, add it as a plugin (e.g., via `sqlite-vec` or separate table) without
  breaking the FTS schema.
- **Consequences:** Semantic similarity queries are not supported in v1. Users
  must use keyword-based memory search.

## ADR-007: No web UI in v1

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Building a good web UI is a project in itself. CLI and chat
  platforms (Telegram, Matrix) provide sufficient interfaces for a v1 personal
  assistant. Web UIs add security surface area (CSRF, XSS, auth).
- **Decision:** No web UI in v1. CLI for local testing, Telegram/Matrix for remote
  access. A read-only status dashboard is a possible future addition.
- **Consequences:** Users must use existing chat clients; no custom web interface
  for interacting with the agent.

## ADR-008: License is Apache 2.0

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Framework intended for public release. MIT is simple but lacks
  explicit patent protection. GPL is too restrictive for a framework. Apache 2.0
  is widely accepted for open infrastructure projects.
- **Decision:** License under Apache 2.0.
- **Consequences:** Contributors grant patent rights. Can be used in commercial
  projects with attribution. Compatible with most other open source licenses.

## ADR-009: count_request correction factor measured but high variance [SUPERSEDED]

- **Status:** Superseded by ADR-011
- **Date:** 2026-04-09
- **Context:** `InferenceClient.count_request()` tokenizes a JSON-serialized request
  body to estimate token count. The actual `prompt_tokens` from llama-server depends
  on the chat template transformation, which is different from raw JSON.
- **Decision:** Measured mean ratio of 1.68 ± 0.84 across 10 conversation shapes.
  High variance (0.57 to 3.45) indicates `count_request` is not reliable for exact
  budgeting. ContextBuilder will use it for rough estimation only; actual overflow
  is handled by the server error response. The correction factor is stored in
  `docs/calibration.json` but is advisory only.
- **Consequences:** Token budgeting is approximate. We may overflow context and get
  a server error in edge cases. The orchestrator should catch and handle this.
  Exact context management requires server-side tokenization which is too slow
  for iterative budget checking.
- **Superseded by:** ADR-011 (two-number calibration is more accurate and safe)

## ADR-010: Handoff docs live in `docs/handoffs/` inside the repo

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Phase 1a report was written to a hermes-context-audit folder outside
  the repo. This makes version history fragmented and risks loss when the external
  folder is cleaned up.
- **Decision:** All Hestia phase reports and handoff documentation live in
  `docs/handoffs/` inside the repository, committed with each phase.
- **Consequences:** Phase reports are versioned with the code they describe.
  Repository size grows slightly with each phase report (acceptable).

## ADR-011: Calibration is two numbers (body factor + meta-tool overhead)

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** ADR-009 accepted a single mean ratio (1.68) as the correction factor
  for `count_request()`, despite high variance (0.57 to 3.45). Analysis of the
  underlying data revealed the variance was bimodal: tool-free requests over-count
  (safe), tool-bearing requests under-count (dangerous). Hestia always sends the
  same two meta-tools, so the tool overhead is a constant.
- **Decision:** Split calibration into `body_factor` (measured on tool-free
  requests, applied as division) and `meta_tool_overhead_tokens` (measured once,
  added as constant when meta-tools are in the request). Formula:
  `corrected = int(predicted_body / body_factor) + meta_tool_overhead_tokens`.
  `count_request()` callers now always pass `tools=[]` for consistency.
- **Consequences:** Budget calculation is now directionally safe (over-counts,
  never under-counts). If we ever add tools beyond the two meta-tools to the
  request, the calibration needs to be extended. Supersedes ADR-009.

## ADR-012: Turn state machine with platform-agnostic confirmation callback

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** The orchestrator needs to run under multiple adapters (CLI
  today, Matrix and Telegram in Phase 2). Some tools require user
  confirmation before executing (e.g., `terminal`). Confirmation UX is
  adapter-specific — CLI uses a stdin prompt, Matrix uses a reply button,
  Telegram uses an inline keyboard. The orchestrator cannot know about
  any of this without coupling itself to every adapter.

  Separately, turn lifecycle needs to be observable and recoverable:
  debugging an agent that hangs mid-turn is impossible without a record
  of what state it was in and what transitions it took.

- **Decision:**
  1. Model the turn lifecycle as an explicit state machine with 10
     states (`RECEIVED`, `BUILDING_CONTEXT`, `AWAITING_MODEL`,
     `EXECUTING_TOOLS`, `AWAITING_USER`, `AWAITING_SUBAGENT`,
     `COMPRESSING`, `RETRYING`, `DONE`, `FAILED`) and a static
     `ALLOWED_TRANSITIONS` table. `assert_transition` raises
     `IllegalTransitionError` on any invalid move. Every transition is
     persisted as a `TurnTransition` row linked to the parent `Turn`.
  2. Tool confirmation is an injected `ConfirmCallback` on the
     `Orchestrator` constructor. The orchestrator never prompts the
     user directly. Adapters provide the callback: CLI calls
     `click.confirm`, Matrix sends a reply with accept/deny buttons,
     Telegram does the same with inline keyboards. If no callback is
     provided and a tool requires confirmation, the call fails closed
     with an error result.
  3. Response delivery uses the same pattern: a `ResponseCallback` the
     adapter provides, invoked when the turn reaches `DONE` or `FAILED`.

- **Consequences:**
  - Adding a new adapter is purely additive — implement two async
    callbacks, inject them into `Orchestrator`, no orchestrator changes.
  - Every turn has a complete transition audit trail in the database,
    which makes post-mortem debugging tractable.
  - Illegal transitions (e.g., skipping `BUILDING_CONTEXT`) fail loudly
    at the source rather than corrupting state silently.
  - The `AWAITING_SUBAGENT` and `COMPRESSING` states are reserved but
    have no transitions wired yet — they'll light up in Phase 3 without
    requiring a schema migration.
  - `requires_confirmation=True` is enforced in the orchestrator on both
    the `call_tool` meta-tool path (which is what models actually use)
    and the direct-tool dispatch path. If `confirm_callback` is `None`
    the orchestrator fails closed with an error result; if the callback
    returns `False` the tool is cancelled.

## ADR-013: SlotManager owns KV-cache slot lifecycle with LRU eviction

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** llama.cpp's server exposes a fixed pool of KV-cache slots
  (configured at startup via `-np N`). Slots dramatically reduce prompt
  processing time for continuation turns because the model reuses the
  cached state instead of re-ingesting the full conversation. But the
  pool is small — on our RTX 3060 we plan to run with 4 slots — and
  multiple sessions can outnumber available slots, so something has to
  decide which sessions get live slots at any moment.

  Without a dedicated manager, each adapter would grow its own ad-hoc
  slot handling, which would quickly diverge and leave stale state in
  the database.

- **Decision:**
  1. Introduce `SlotManager` as a new policy layer on top of
     `InferenceClient`. It owns the slot-id-to-session-id assignment
     map, the on-disk directory for saved slot state, and the pool size.
  2. Sessions have a temperature: `COLD` (no slot, no disk state),
     `WARM` (disk-backed, can be restored), `HOT` (live slot assigned).
     The manager transitions sessions through these states via the
     `SessionStore` as the single source of truth.
  3. `acquire(session)` guarantees the session has a live slot at turn
     start, restoring from disk if WARM, allocating fresh if COLD, or
     reusing the existing slot if HOT. If the pool is full, the
     least-recently-used session is evicted (save to disk + erase slot +
     demote to WARM) and its slot is reassigned.
  4. `save(session)` checkpoints slot state to disk after each successful
     turn without demoting temperature. The slot stays HOT; the disk
     file is a backup for eventual eviction or server restart.
  5. All SlotManager operations are serialized by a single asyncio Lock.
     Per-turn work inside the orchestrator runs outside the lock.

- **Consequences:**
  - Session resumption is fast: a WARM session's next turn skips the
    prompt re-ingestion entirely because llama.cpp restores the KV cache
    from disk.
  - The pool size is a hard tuning knob — too small and sessions thrash,
    too big and GPU memory runs out. We start at 4 for the 3060 build
    and plan to expose it as a CLI option.
  - Eviction is LRU by `last_active_at`. More sophisticated policies
    (priority, user-pinning) can replace `_pick_lru_victim` without
    changing the public API.
  - If the inference server restarts, all in-memory slot assignments
    vanish but disk state survives. The manager detects the mismatch
    via the `_assignments` map check in `acquire()` and transparently
    reallocates + restores. This is best-effort — if the restart
    happens mid-turn, that turn will fail and the user will have to
    retry.
  - Save failures during eviction propagate as hard errors rather than
    silently leaking state. The alternative (swallowing and continuing)
    would leave the database believing a session is WARM with a saved
    path that doesn't exist on disk.

## ADR-014: Scheduler runs scheduled tasks via the existing Orchestrator

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Hestia needs to fire LLM turns at user-defined times — both
  recurring ("every weekday at 9am, summarize my Matrix unread") and one-shot
  ("remind me at 3pm"). Without a dedicated scheduler, every adapter would
  end up reinventing this loop, and the natural place for it (cron + a
  daemon process) lives outside Hestia entirely, which loses session
  continuity and KV-cache reuse.

- **Decision:**
  1. Introduce a `Scheduler` class that owns a single asyncio loop. The loop
     wakes on a fixed tick interval, queries `SchedulerStore.list_due_tasks`,
     and fires each due task by invoking the existing `Orchestrator.process_turn`
     with the task's prompt as a synthetic user message.
  2. Scheduled tasks are persisted in a new `scheduled_tasks` table that
     stores either a `cron_expression` (recurring) or a `fire_at` timestamp
     (one-shot), never both. `next_run_at` is computed eagerly with
     `croniter` and updated after every run.
  3. The Scheduler does not own its own `InferenceClient` or `SlotManager` —
     it receives an already-built `Orchestrator`. This guarantees scheduled
     turns share the same slot pool, calibration, and policy as
     interactive turns.
  4. Task results are delivered via a `response_callback` injected at
     construction. The CLI daemon prints to stdout. Future adapters
     (Matrix, Telegram) will route the response back to the originating
     channel.
  5. One-shot tasks auto-disable after firing because `_compute_next_run`
     returns `None` for them. Recurring tasks advance `next_run_at` to
     the next cron occurrence.
  6. The loop is cancellable via an `asyncio.Event`. `stop()` is fast and
     idempotent.

- **Consequences:**
  - Scheduled and interactive turns are indistinguishable from the
    Orchestrator's perspective, so all the Phase 1c invariants
    (transition validation, EmptyResponseError guard, confirmation
    enforcement) apply uniformly.
  - Scheduled turns benefit from KV-cache reuse: a recurring task that
    runs against the same session every morning will warm-restore the
    slot from disk on each fire.
  - Task firing is sequential within a tick. If a task takes 30 seconds
    and ten tasks are due at once, the tenth waits five minutes. This is
    fine for Phase 2b — the realistic load is single-digit tasks per day.
    A worker pool can be added later without changing the public API.
  - Cron expressions are evaluated in the process's local timezone, not
    UTC. This matches user intuition for "every weekday at 9am" but
    needs to be documented.
  - One-shot tasks scheduled in the past are silently disabled (their
    `next_run_at` is `None` from the start). The CLI rejects past
    `--at` values up front so the user gets a clear error.
  - Adding `croniter` is the first non-stdlib runtime dependency outside
    httpx/sqlalchemy/click. It's small, stable, and widely used; the
    alternative (hand-rolled cron parsing) is not worth the bug surface.
