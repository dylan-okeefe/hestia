# Changelog

All notable changes to this project will be documented in this file.
Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.7.5] — 2026-04-18

### Changed
- **Orchestrator engine cleanup (L31).** Pure refactor of `process_turn` and
  `_dispatch_tool_call` in `src/hestia/orchestrator/engine.py`:
  - Extracted `_build_failure_bundle(...)` to eliminate ~120 lines of duplicated
    failure-bundle construction across the `ContextTooLargeError` and generic
    `Exception` handlers.
  - Hoisted `delegated` and `tool_chain` to the top of the outer `try` block,
    removing the defensive `locals().get("delegated", False)` smell.
  - Removed the duplicate `get_messages` round-trip after `DONE`; artifact
    handles are now accumulated directly from `ToolCallResult.artifact_handle`
    during tool dispatch, deleting the regex-based `re.findall(r"artifact://...")`
    recovery path.
  - Extracted `_check_confirmation(...)` to deduplicate the confirmation gate
    across the `call_tool` meta branch and the direct-tool branch.
  - Added `ToolCallResult.error(content)` classmethod in
    `src/hestia/tools/types.py`; replaced 8+ long-form error constructions in
    `engine.py`.
  - File shrank from 903 lines to ≤ 750 (target met).

### Added
- Regression test modules:
  - `tests/unit/test_orchestrator_failure_bundle.py` — parity coverage for
    `_build_failure_bundle` from both error paths.
  - `tests/unit/test_orchestrator_confirmation_helper.py` — unit coverage for
    `_check_confirmation` (no-confirm, approved, denied, no-callback).
  - `tests/unit/test_orchestrator_artifact_accumulation.py` — asserts that
    artifact handles flow from `ToolCallResult` into trace records and that the
    regex recovery path is gone.

## [0.7.4] — 2026-04-18

### Changed
- **`cli.py` decomposition (ADR-0020).** Split the 2,569-line monolith into:
  - `src/hestia/app.py` (≈1,520 lines) — `CliAppContext`, `make_app(config)`,
    lazy subsystem properties, idempotent `bootstrap_db()`, single
    `make_orchestrator()` constructor, and all `_cmd_*` async command
    implementations (chat, ask, schedule, reflection, skill, style, audit,
    email, status, health, policy, failures).
  - `src/hestia/platforms/runners.py` (≈245 lines) — `run_telegram(app, config)`,
    `run_matrix(app, config)`, and a shared `run_platform(...)` polling helper.
  - `src/hestia/cli.py` (≤ 600 lines) — slim Click definitions only; every
    command is `@run_async`-decorated and reads `app: CliAppContext` from
    `ctx.obj`.
  - Pure refactor: identical test suite (691 passed, 6 skipped, 0 mypy errors)
    apart from new tests covering `app.py` and `runners.py` wiring.

### Added
- `run_async` decorator (in `hestia.app`) that converts an `async def cmd(app, ...)`
  function into a Click-compatible sync handler running on a fresh event loop.
- ADR-0020: cli.py decomposition rationale and module ownership boundaries.

### Fixed
- `Orchestrator(...)` is now constructed in exactly one place
  (`CliAppContext.make_orchestrator()`); `cli.py`, `schedule daemon`,
  `telegram`, and `matrix` all go through it. Adding a new dependency to the
  orchestrator is now a single-call-site change.
- Dropped the duplicated raw `ctx.obj["..."]` dict layer; commands read from
  the typed `CliAppContext` only.
- Ruff cleanup: 64 auto-fixable lints in cli/persistence/skills/platforms
  resolved (unused imports, import-sort, `OSError`/`IOError` alias,
  `datetime.UTC`, etc.). Remaining `ruff check src/` count is now 44
  (down from 255 on develop).

## [0.7.3] — 2026-04-18

### Added
- Reflection scheduler failure visibility: `ReflectionScheduler` now records failures in a ring buffer (max 20) keyed by stage (`mining`, `proposal`, `tick`). `hestia reflection status` prints scheduler health including failure count and last errors.
- Style scheduler failure visibility: `StyleScheduler` records failures in the same ring-buffer pattern. `hestia style show` displays a `Failures:` section when the scheduler is degraded.
- `EmailConfig.password_env` for credentials-from-environment. The env-var pattern is now the primary recommendation in `docs/guides/email-setup.md`.
- `HESTIA_SOUL_PATH` and `HESTIA_CALIBRATION_PATH` environment overrides. The CLI warns (yellow, stderr) when `SOUL.md` or `docs/calibration.json` is missing.

### Fixed
- `WebSearchConfig.provider` narrowed from `str` to `Literal["tavily", ""]` to match the actual support matrix. Removed unimplemented `"brave"` from docstring.

### Changed
- `SECURITY.md` refreshed for 0.7.x: supported versions table updated, new "Trust profiles" subsection, new "Egress audit" subsection, new "Prompt-injection scanner" subsection, and a real disclosure address (GitHub Security Advisories).
- ADRs consolidated: moved `docs/development-process/decisions/*.md` into `docs/adr/`. Updated cross-references in `README.md`, handoffs, and `KIMI_CURRENT.md`.

## [0.7.2] — 2026-04-18

### Fixed
- Replaced archived `bleach` dependency with actively-maintained `nh3` for HTML
  sanitization in email bodies. `nh3` is Rust-backed and ships type stubs.
- Registered missing `read_artifact` tool in CLI tool registry.
- Added `delete_memory` tool (requires confirmation) to complement `save_memory`,
  `search_memory`, and `list_memories`.
- `EmailAdapter.create_draft` now generates a real `Message-ID` before IMAP
  `APPEND`, fixing the UID lookup that previously always fell back to the
  `"draft-unknown"` sentinel.
- Removed `"draft-unknown"` sentinel: `create_draft` raises `EmailAdapterError`
  when the draft cannot be located by Message-ID, and `send_draft` rejects the
  placeholder ID explicitly.
- Hardened `_parse_search_query` against IMAP injection: all interpolated tokens
  are quoted with backslash/quote escaping before entering IMAP `SEARCH`
  criteria.
- Malformed `SINCE:` dates (e.g. `2026-99-99`) now raise `EmailAdapterError`
  instead of silently falling through to a subject search.

### Removed
- Dead `StyleProfileBuilder.get_profile_dict()` synchronous stub. The real
  async implementation lives on `StyleStore`.

## [0.7.1]

### Added
- `StyleProfile` system for per-user interaction-style adaptation.
  - `StyleConfig` dataclass (`enabled`, `min_turns_to_activate`, `lookback_days`, `cron`)
    wired through `HestiaConfig`.
  - `StyleProfileStore` with `style_profiles(platform, platform_user, metric, value_json,
    updated_at)` table.
  - `StyleProfileBuilder` recomputes four metrics nightly from traces: `preferred_length`,
    `formality`, `top_topics`, `activity_window`. No LLM calls in v1.
  - `StyleScheduler` shares the same idle gate as `ReflectionScheduler` and runs via
    cron in the scheduler daemon.
  - `ContextBuilder` gains a `style_prefix` slot injected as the last prefix layer.
  - Orchestrator wires style prefix per-session when enabled and threshold is met.
  - CLI surface: `hestia style show`, `hestia style reset`, `hestia style disable`.
  - ADR-0019 documenting the separation between operator-authored identity and
    observed style profile.
  - Privacy note: style metrics live only in the local SQLite DB and never leave
    the machine.

## [0.7.0]

### Added
- `ReflectionRunner` three-pass pipeline (pattern mining → proposal generation →
  queue write) in `src/hestia/reflection/runner.py`.
- `Proposal` schema and `ProposalStore` with `pending/accepted/rejected/deferred/expired`
  lifecycle in `src/hestia/reflection/store.py`.
- `ReflectionConfig` dataclass (`enabled`, `cron`, `idle_minutes`, `lookback_turns`,
  `proposals_per_run`, `expire_days`, `model_override`) wired through `HestiaConfig`.
- Scheduler integration: `ReflectionScheduler` checks cron + idle rules and runs
  reflection during the scheduler daemon loop.
- Session-start hook: when pending proposals exist, the orchestrator injects a
  one-time system note on the first turn of a new session.
- CLI surface: `hestia reflection status/list/show/accept/reject/defer/run/history`.
- ADR-0018 documenting the three-pass design and why proposals are never auto-applied.
- `docs/guides/reflection-tuning.md` with operator guidance on interpreting proposals,
  tuning cron / lookback, and handling false positives.
- Unit tests: `tests/unit/test_reflection_runner.py`, `tests/unit/test_proposal_lifecycle.py`.
- Integration tests: `tests/integration/test_reflection_scheduler.py`,
  `tests/integration/test_session_start_proposals.py`.

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
