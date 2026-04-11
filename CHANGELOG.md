# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **Phase 6: Hardening & Observability**
  - Capability labels for tools (`read_local`, `write_local`, `shell_exec`, etc.)
  - Session-aware tool filtering via `PolicyEngine.filter_tools()`
  - Path sandboxing for file operations with `allowed_roots` configuration
  - Typed failure tracking with `FailureClass` enum and `FailureStore` persistence
  - Centralized logging with `setup_logging()`
  - CLI commands: `version`, `status`, `failures list/summary`
  - Store query methods for status reporting (`count_sessions_by_state`, `turn_stats_since`, `summary_stats`)

- **Phase 5: Subagent Delegation**
  - `delegate_task` tool for subagent spawning
  - `SubagentResult` envelope for structured responses
  - `AWAITING_SUBAGENT` state in turn lifecycle
  - `PolicyEngine.should_delegate()` with heuristics
  - Session ID threading via `contextvars` for memory attribution

- **Phase 4: Long-Term Memory**
  - `MemoryStore` with FTS5 full-text search
  - Memory tools: `search_memory`, `save_memory`, `list_memories`
  - CLI memory commands: `hestia memory search/list/add/remove`
  - Session context tracking for memory attribution

- **Phase 3: Scheduler & Platforms**
  - `Scheduler` with cron and one-shot task support
  - `SchedulerStore` for task persistence
  - CLI scheduler commands: `add`, `list`, `show`, `run`, `enable`, `disable`, `remove`, `daemon`
  - Telegram adapter with long-polling
  - Crash recovery for stale turns and sessions

- **Phase 2: KV Cache Management**
  - `SlotManager` for llama.cpp KV-cache slot allocation
  - HOT/WARM/COLD temperature states for sessions
  - Slot save/restore to disk for memory pressure handling
  - LRU eviction policy

- **Phase 1: Core Framework**
  - `InferenceClient` for llama.cpp server (tokenize, chat, slot ops)
  - `SessionStore` with SQLAlchemy Core async
  - `ContextBuilder` with token budgeting and calibration
  - `ToolRegistry` with `@tool` decorator
  - `Orchestrator` with 10-state turn machine
  - Built-in tools: `current_time`, `http_get`, `list_dir`, `read_file`, `write_file`, `terminal`
  - CLI commands: `chat`, `ask`, `init`, `health`
  - Alembic migrations

## [0.0.0] - 2026-04-09

### Added
- Initial scaffold (README, LICENSE, .gitignore, pyproject.toml)
