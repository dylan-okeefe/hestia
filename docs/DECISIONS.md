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
- `requires_confirmation=True` tools will run unconfirmed if an
  adapter forgets to wire the callback, so the orchestrator fails
  closed in that case (see commit fixing the fail-open bug).
