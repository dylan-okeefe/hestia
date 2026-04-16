# Changelog

All notable changes to this project will be documented in this file.
Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.2.0] — 2026-04-15

### Added
- `MatrixAdapter` implementing Platform ABC with `matrix-nio`
- `hestia matrix` CLI command
- `MatrixConfig` dataclass
- ADR-021
- `IdentityConfig` and `IdentityCompiler` for deterministic identity extraction
- `MemoryEpochCompiler` for 30-day memory epochs in context
- `TraceStore` and `FailureStore` with enriched fields
- `SkillStore`, `SkillIndexBuilder`, and skill lifecycle management
- `SecurityAuditor` with `hestia audit` and `hestia policy show` CLI commands
- `CONTRIBUTING.md`
- GitHub Actions CI workflow (`.github/workflows/ci.yml`)

### Changed
- Unified `utcnow()` adoption across the entire `src/` tree
- Narrowed exception catches in orchestrator, CLI, and stores
- Populated enriched `FailureBundle` fields (`request_summary`, `policy_snapshot`, `slot_snapshot`, `trace_id`)

### Fixed
- `tool_chain` UnboundLocalError in orchestrator error handler
- `db.py` import ordering
- Path sandboxing for `list_dir`
- Deduplicated `CliConfirmHandler`
- Removed unsandboxed `read_file` / `write_file` fallbacks
- SSRF protection on `http_get`
- Removed dead `COMPRESSING` state

### Added — Phase 6: Hardening & observability
- Capability labels for tools (`read_local`, `write_local`, `shell_exec`,
  `network_egress`, `memory_read`, `memory_write`, `orchestration`)
- `PolicyEngine.filter_tools()` — session-aware tool filtering
- Path sandboxing for file operations with `allowed_roots` configuration
- Typed failure tracking with `FailureClass` enum and `FailureStore`
- Centralized logging via `setup_logging()`
- CLI commands: `version`, `status`, `failures list`, `failures summary`
- Store query helpers: `count_sessions_by_state`, `turn_stats_since`,
  `summary_stats`

### Added — Phase 5: Subagent delegation
- `delegate_task` tool for spawning subagents
- `SubagentResult` envelope for bounded context growth (~300 tokens)
- `AWAITING_SUBAGENT` state in turn lifecycle
- `PolicyEngine.should_delegate()` with heuristics
- Session ID threading via `contextvars` for memory attribution

### Added — Phase 4: Long-term memory
- `MemoryStore` with FTS5 full-text search and BM25 ranking
- Memory tools: `search_memory`, `save_memory`, `list_memories`
- CLI memory commands: `memory search`, `memory list`, `memory add`,
  `memory remove`
- Session context tracking for memory attribution

### Added — Phase 3: Telegram adapter
- `TelegramAdapter` implementing Platform ABC
- HTTP/1.1 forced for Telegram API stability (ADR-016)
- Rate-limited `edit_message` (max 1 per 1.5s)
- User allowlist via `TelegramConfig.allowed_users`
- Crash recovery for stale turns and sessions on startup
- `hestia telegram` CLI command

### Added — Phase 2c: Config & platform base
- `HestiaConfig` typed dataclass with sub-configs (ADR-015)
- Platform ABC with `start`, `send_message`, `edit_message`, `send_error`
- CLI adapter refactored to implement Platform ABC
- Alembic migration setup with initial migration
- `write_file`, `list_dir`, `http_get` built-in tools

### Added — Phase 2b: Scheduler
- `Scheduler` with cron and one-shot task support (ADR-014)
- `SchedulerStore` for task persistence with croniter
- CLI scheduler commands: `add`, `list`, `run`, `enable`, `disable`,
  `remove`, `daemon`

### Added — Phase 2a: KV-cache management
- `SlotManager` for llama.cpp KV-cache slots (ADR-013)
- HOT/WARM/COLD temperature states
- LRU eviction with save/restore to disk

### Added — Phase 1c: Orchestrator & CLI
- `Orchestrator` with 10-state turn machine (ADR-012)
- Platform-agnostic `ConfirmCallback` and `ResponseCallback`
- CLI commands: `chat`, `ask`, `init`, `health`
- Integration tests for full turn lifecycle

### Added — Phase 1b: Tools & context
- `ToolRegistry` with `@tool` decorator and meta-tool pattern (ADR-011)
- `ContextBuilder` with token budgeting and two-number calibration
- `ArtifactStore` for large tool output storage
- Built-in tools: `current_time`, `read_file`, `terminal`, `read_artifact`

### Added — Phase 1a: Core foundation
- `InferenceClient` for llama.cpp server (tokenize, chat, slot ops)
- `SessionStore` with SQLAlchemy Core async
- Database schema and connection management
- Calibration measurement tooling

## [0.1.0] — 2026-04-09

Initial milestone tag marking completion of Phase 1c (orchestrator + CLI). Not a
public release — see [0.2.0] for the first public version.

## [0.0.0] — 2026-04-09

### Added
- Initial scaffold (README, LICENSE, .gitignore, pyproject.toml)
