# Changelog

All notable changes to this project will be documented in this file.
Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.6.0]

### Added
- `EmailAdapter` in `src/hestia/email/adapter.py` with IMAP read/search and
  SMTP/IMAP draft flow. Uses stdlib `imaplib`/`smtplib` + `bleach` for HTML
  sanitization.
- `EmailConfig` dataclass (`imap_host`, `smtp_host`, `username`, `password`,
  `sanitize_html`, etc.) wired through `HestiaConfig`.
- Email tools: `email_list`, `email_read`, `email_search`, `email_draft`,
  `email_send`, `email_move`, `email_flag`. `email_send` requires confirmation
  (`requires_confirmation=True`) and is gated by trust profile.
- `TrustConfig.subagent_email_send` and `TrustConfig.scheduler_email_send`
  (both default `False`) to prevent headless contexts from triggering outbound
  mail.
- `EMAIL_SEND` capability label for policy-engine filtering.
- `hestia email check/list/read` CLI commands for operator diagnostics.
- `docs/guides/email-setup.md` with app-password walkthroughs for Gmail and
  Fastmail.
- Integration test `tests/integration/test_email_roundtrip.py` mocking IMAP
  and SMTP for draft → list → send workflow.
- Unit test `tests/unit/test_email_sanitization.py` covering HTML stripping,
  body truncation, injection scanner interaction, and search query parsing.

### Changed
- Bumped version to 0.6.0 (minor — new platform-level capability).

## [0.5.1]

### Added
- `InjectionScanner` in `src/hestia/security/injection.py` scans tool results for
  known prompt-injection patterns and high-entropy content before they enter the
  model context. Hits are annotated, never blocked.
- `SecurityConfig` dataclass (`injection_scanner_enabled`, `injection_entropy_threshold`,
  `egress_audit_enabled`) wired through `HestiaConfig`.
- Egress audit logging: `http_get` and `web_search` record every outbound request
  to a new `egress_events` table via `TraceStore.record_egress()`.
- `hestia audit egress --since=7d` CLI subcommand prints domain-level aggregation
  with anomaly heuristics (low-volume and first-time domains).
- ADR-0017 documenting the injection-detection and egress-audit design.
- `SECURITY.md` with supported versions, reporting process, and configuration guide.

### Fixed
- Pre-existing mypy errors in `matrix_adapter.py` and `telegram_adapter.py`
  (`asyncio.wait_for` receiving `Future | None`).

## [0.4.1]

### Fixed
- Unchecked `Optional` access on SchedulerStore and SkillState that could NPE
  in CLI commands.
- Telegram adapter `Updater` lifecycle raised when `stop()` was called before
  `start()`.
- `turn_token_budget` NPE in `hestia check` with no active session.
- Strict coercion for ScheduledTask row conversion prevents NULL `enabled`
  from passing a truthiness check incorrectly.
- Tool call dispatch rejects malformed `arguments` payloads instead of
  passing `None` into the registry.

### Changed
- CI now runs `mypy src/hestia` with no baseline (0 errors).
- `hestia.policy.*` and `hestia.core.*` are strict-typed.

## [0.4.0]

### Added
- `HandoffConfig` controls automatic session-close summaries.
- `CompressionConfig` enables `HistoryCompressor` to splice summaries of
  dropped history into context when the budget is tight.
- `send_system_warning` on `Platform` ABC for out-of-band operator messaging.

### Changed
- `ContextBuilder.build` raises `ContextTooLargeError` when protected context
  exceeds budget instead of silently best-efforting.
- `TrustConfig.household()` / `developer()` now imply handoff and compression.

### Fixed
- (none — no prior regressions)

## [0.2.2] — 2026-04-17

### Fixed
- `SlotManager` now passes only the basename of a slot file to llama.cpp's
  `/slots?action=save|restore` endpoint. Previously Hestia sent absolute
  paths, which llama.cpp rejects (HTTP 400 "Invalid filename"), causing
  every turn to log an error and no session state ever reached disk. A
  one-time migration normalizes any existing `sessions.slot_saved_path`
  values to basenames.
- `DefaultPolicyEngine.ctx_window` is now wired through `HestiaConfig.inference.context_length`
  (new field). Previously the policy always used the 32768 default
  regardless of the user's actual llama-server `--ctx-size / --parallel`
  settings, silently over-committing the turn token budget on typical
  12GB deployments.

### Changed
- `SlotConfig.slot_dir` docstring clarified: this must match llama-server's
  `--slot-save-path`. Hestia does **not** write to this directory; it is
  a declaration so out-of-band cleanup knows where to look.
- README quickstart now shows `turbo3` KV-cache quantization (matching
  `deploy/hestia-llama.service`), not `q4_0`.
- `DefaultPolicyEngine.ctx_window` default changed from 32768 to 8192 to
  match `deploy/hestia-llama.service` out of the box. Users on larger
  servers should set `InferenceConfig.context_length` explicitly.

## [0.2.1] — 2026-04-15

### Fixed
- `SecurityAuditor` trace-pattern check now uses the real tool name `save_memory`
  instead of the stale alias `memory_write`. The "save_memory after http_get"
  warning previously never fired on real data.
- `ArtifactStore` per-artifact metadata writes are now atomic
  (`tempfile.mkstemp` + `os.replace`), matching the inline-index fix from v0.2.0.

### Changed
- AI-orchestration documentation (`docs/orchestration/`, `docs/prompts/`, internal
  reviews and brainstorms) moved to `docs/development-process/` with an
  explanatory README. The public `docs/` tree now contains only user-facing
  documentation, ADRs, and operator runbooks.
- CI mypy step is now baseline-aware: 44 pre-existing errors are recorded in
  `docs/development-process/mypy-baseline.txt`; new errors fail CI.

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
