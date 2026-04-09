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

## ADR-009: count_request correction factor measured but high variance

- **Status:** Accepted
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
