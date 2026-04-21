# Changelog

All notable changes to this project will be documented in this file.
Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.9.1] — 2026-04-20

Patch release. Consolidates the Copilot audit backlog from v0.9.0
(39 items triaged into high/medium/low/test-gap/architecture) plus
email-cleanup, memory-cleanup, and policy-and-inference fixes.
No new features; all changes are bug fixes, hardening, and internal
quality.

### Security & hardening
- `HestiaConfig` now rejects `model_name == "dummy"` at load time.
- Injection-scanner regex is anchored and requires minimum length.
- `SECURITY.md` notes that `config.py` executes arbitrary Python
  (standard for Python projects but worth stating).
- `TrustConfig` presets (`paranoid`, `household`, `developer`,
  `prompt_on_mobile`) are now cached to avoid object-identity bugs in
  `for_trust()` equality checks. `HestiaConfig.for_trust()` also caches
  its inverse lookup.
- `hestia doctor` warns when `allowed_roots` contains `"."`.

### Reliability
- `ReflectionScheduler.wire_failure_handler(runner)` is now a public
  method; `app.py` no longer reaches into the scheduler's private
  `_record_failure` attribute.
- Scheduler tick loop uses `contextlib.suppress(TimeoutError)` instead
  of a bare `except TimeoutError: pass`.
- `DefaultPolicyEngine` uses a module-level logger instead of
  `print()` for policy-failure diagnostics.
- Subagent `artifact_handles` are propagated through `delegate_task`
  so artifacts created by a subagent are visible to the parent session.
- Email adapter guards `conn.close()` to the `SELECTED` state and
  narrows bare `except:` blocks.

### Internal quality
- Consolidated duplicate `traces` DDL inline strings into
  `schema.py`.
- `EmailConfig.drafts_folder` / `sent_folder` are configurable.
- Scheduler respects `config.system_prompt` instead of a hard-coded
  fallback.
- Memory store param-binding is consistent across all methods.
- Tool docstring boilerplate deduplicated in `list_dir`, `read_file`,
  `write_file`.
- Pre-existing smoke test import fixed for `read_file` factory pattern.

## [0.9.0] — 2026-04-19

First release after `v0.8.0`. Ships the multi-user safety train on top of a
voice-message MVP and an internal-quality cleanup. Two new feature areas
(voice messages, multi-user support) plus a one-way memory schema migration
justify the minor bump.

### Multi-user support (L45 train)
- **L45a** — Runtime identity plumbing. New `current_platform` and
  `current_platform_user` `ContextVar`s are set by the orchestrator on every
  turn (success and failure paths) so downstream code can scope behavior to
  the calling user. New `HestiaConfig.trust_overrides: dict[str, TrustConfig]`
  keyed by `"platform:platform_user"` lets operators grant different trust
  profiles per identity. `DefaultPolicyEngine._trust_for(session)` resolves
  the effective profile per call (`auto_approve`, `filter_tools`), falling
  back to the default with a warning when identity is missing. Scheduler
  tasks inherit the creator's identity via the session, so policy decisions
  on background ticks use the right profile instead of a global default.
- **L45b** — Per-user memory scoping. Adds a one-way FTS5 recreate-and-copy
  migration that introduces `platform` and `platform_user` columns on the
  `memory` table and backfills them from `sessions`; rows that cannot be
  backfilled land under `__legacy__`. `MemoryStore.save/search/list_memories/
  delete/count` take optional `platform`/`platform_user` and otherwise fall
  back to the runtime ContextVars — queries without identity filter to that
  identity (fail-closed). `save_memory` reads identity from ContextVars
  explicitly; `search_memory`/`list_memories` ride the store fallback.
  `MemoryEpochCompiler` now compiles per session identity, so epochs never
  leak another user's facts. FTS5-unavailable builds get a regular table +
  `LIKE`-based search with exact-tag matching.
- **L45c** — Allow-list hardening and multi-user docs. New
  `src/hestia/platforms/allowlist.py` with a shared `fnmatch`-based
  `match_allowlist()` plus platform validators for Telegram user IDs,
  Telegram usernames, and Matrix room IDs/aliases. `TelegramAdapter` and
  `MatrixAdapter` use the shared matcher (numeric IDs case-sensitive,
  usernames/rooms per platform convention) and warn on startup for
  allow-list entries that look invalid but are not wildcard patterns.
  New `docs/guides/multi-user-setup.md` covers the security model, allow-list
  configuration, per-user trust overrides, and troubleshooting; README gains
  a "Multi-user security" subsection and mentions
  `TrustConfig.prompt_on_mobile()` alongside the other presets.

### Voice messages (Phase A)
- **L41** — Shared voice infrastructure. New `hestia.voice` package with a
  transport-agnostic `VoicePipeline` (lazy faster-whisper STT + Piper TTS,
  sentence-level streaming synthesis, singleton accessor, import-safe when
  the `voice` extra isn't installed). New `VoiceConfig` dataclass, new
  `hestia[voice]` extra (`faster-whisper`, `piper-tts`), `hestia doctor`
  check for the voice prerequisites, and a setup guide with VRAM budget
  guidance for the RTX 3060 target.
- **L42** — Telegram voice-message handler behind
  `TelegramConfig.voice_messages` (default off). Incoming voice notes are
  downloaded, transcoded OGG/Opus → PCM via `ffmpeg`, transcribed, fed to
  `Orchestrator.process_turn()` as a normal text turn, and the reply is
  synthesized → OGG/Opus → `reply_voice()`. If the reply exceeds Telegram's
  ~1 MB voice-note limit, Hestia iteratively truncates the audio and sends
  the full text as a follow-up so no content is silently dropped.
  Destructive-tool confirmation still uses the existing inline-keyboard
  flow; verbal confirmations are deferred to Phase B (L43).

### Internal quality (L40 — Copilot cleanup)
- Tool dispatch is now concurrent by default: `Orchestrator._execute_tool_calls`
  partitions tool calls into concurrent and serial buckets, runs the
  concurrent ones under `asyncio.gather`, and preserves emission order when
  reassembling results. New `metadata.ordering` field ("concurrent"/"serial",
  default "concurrent"); all email tools are marked `serial` because IMAP
  session reuse + confirmation make sequential the safer default.
- Removed the `should_evict_slot` stub from `PolicyEngine` /
  `DefaultPolicyEngine` (and all `FakePolicyEngine` shims), along with
  stale `TODO(L31)` and `TODO(L?)` markers across the orchestrator engine,
  slot manager, style builder, audit checks, and doctor.
- `EmailConfig.drafts_folder` / `sent_folder` are now configurable (default
  "Drafts"/"Sent") so Gmail deployments can point at `[Gmail]/Drafts` etc.
  `EmailAdapter` narrowed three bare `except:` blocks and guards
  `conn.close()` to the `SELECTED` state, fixing sporadic
  `IMAP4.error: command CLOSE illegal in state AUTH` on reconnect.
- `HestiaConfig.prompt_on_mobile` docstring now matches the fire-and-forget
  callback implementation. Regression test added for `for_trust` value
  equality so trust-preset dispatch survives object recreation.

### Migration notes
- The FTS5 `memory` migration is one-way and automatic on first boot of
  `v0.9.0`. Rows that can't be joined back to a session's identity are
  attributed to `__legacy__`; operators can reassign via the admin helper
  described in `docs/guides/multi-user-setup.md`.
- `hestia[voice]` is opt-in. Deployments that don't install the extra see
  no new runtime dependencies; `hestia doctor` will flag missing voice
  prerequisites only when `VoiceConfig` or `TelegramConfig.voice_messages`
  is actually enabled.
- Allow-list wildcard support is additive: existing exact-match
  `allowed_users` / `allowed_rooms` entries continue to work unchanged.

### Pre-release hotfixes (2026-04-20 Copilot audit response)

Ships with the v0.9.0 tag. A larger backlog of ~39 additional audit
findings is tracked in
`docs/development-process/prompts/v0.9.1-copilot-backlog.md` for v0.9.1.

- fix(persistence): use `utcnow()` in `trace_store.record_egress` so
  egress `created_at` is tz-aware UTC and joins correctly against the
  rest of the schema (C-1).
- fix(persistence): close the TOCTOU race on `SessionStore.append_message`
  and `append_transition` by retrying on `IntegrityError`. Regression
  test in `tests/unit/test_append_message_race.py` spawns 20 concurrent
  appenders and asserts 20 distinct `idx` values (C-2 / T-1).
- fix(artifacts): `tools/registry.py` and `tools/builtin/read_artifact.py`
  now offload `ArtifactStore.store` / `fetch_content` via
  `asyncio.to_thread` so large-artifact I/O doesn't block the event
  loop. New `ArtifactStore.open()` async factory for async-first
  construction (C-3).
- fix(orchestrator): `engine.process_turn` raises typed
  `MaxIterationsError` / `PolicyFailureError` instead of bare
  `Exception`. Classifier keeps `FailureClass.MAX_ITERATIONS` and gains
  the type-map entry; string-match fallback preserved for legacy
  callers (C-4).
- fix(doctor): `_check_dependencies_in_sync` uses
  `asyncio.create_subprocess_exec`; `_check_llamacpp_reachable` uses
  `httpx.AsyncClient`. Doctor no longer stalls the event loop for up to
  12 s while other async work is in flight (C-5).
- fix(email): `_smtp_connect` uses `smtplib.SMTP_SSL` on port 465
  (implicit TLS) and now asserts the `STARTTLS` response code is 220
  before sending credentials on other ports — a refused upgrade used to
  silently leave the session cleartext (C-6).
- fix(inference): guard empty-choices responses from llama-server (H-1)
  and raise a typed error when a model emits tool-call arguments that
  are not a JSON object (H-2).
- fix(tools): `write_file.py` and the CLI audit-report writer now pass
  `encoding="utf-8"` explicitly (H-3). `web_search` sends the Tavily
  API key as an `Authorization: Bearer` header instead of embedding it
  in the request body (H-4).
- fix(tools): `ToolRegistry.call` widens the handler exception contract
  to broad `Exception` (not `BaseException` — `CancelledError` still
  propagates) and wraps in a new `ToolExecutionError`. `ToolCallResult`
  gains an optional `error_type` so the orchestrator can classify tool
  failures without string-matching (H-9).
- fix(policy): `PolicyEngine` ABC declares `ctx_window: int` so
  subclasses that don't inherit `DefaultPolicyEngine` no longer
  `AttributeError` from `commands.py`. Contract test in
  `tests/unit/test_policy_engine_ctx_window.py` (A-3).

## [0.8.0] — 2026-04-19

The first major release since `v0.2.2` (April 11). Rolls up the eight-month
arc of work that turned Hestia from "scaffold + matrix adapter" into a
public-ready, security-hardened, multi-platform local assistant.

### Trust & confirmations
- **L20** — Trust profiles (`TrustConfig`) gating destructive tools, plus web-search integration (`web_search` tool via Tavily).
- **L23** — Platform confirmation callbacks: Telegram inline keyboards, Matrix reply pattern, shared `ConfirmationStore`. Destructive tools now require explicit user approval per platform.

### Context & resilience
- **L21** — Session handoff summaries, history compression, loud `ContextTooLargeError` warnings, and `send_system_warning` platform channel.
- **L32** — Context-builder rework: dead `TurnState`/`ToolResult` removed, ordered `_PrefixLayer` registry, per-message `/tokenize` cache (amortized O(1) tokenize calls per build for unchanged messages). ADR-0021.

### Architecture & quality
- **L22** — Mypy strictness ratchet: 44 → 0 errors. CI now fails on any new type error.
- **L30** — CLI decomposition: 2,569-line `cli.py` monolith split into `app.py` (`CliAppContext`, command bodies) + `platforms/runners.py` (Telegram/Matrix runtime loops) + 588-line slim `cli.py`. ADR-0020. Ruff baseline collapsed from 255 → 44.
- **L31** — Orchestrator engine cleanup: extracted `_build_failure_bundle` (killed duplicated except-block bodies), hoisted `delegated`/`tool_chain` state, single `get_messages` per turn, artifact accumulation from `ToolCallResult.artifact_handle` (not regex), extracted `_check_confirmation`, new `ToolCallResult.error` classmethod.

### Security
- **L24** — Prompt-injection scanner (`InjectionScanner`) with regex pattern + entropy heuristics; egress auditing (`hestia audit egress`).
- **L33a** — `InjectionScanner` threshold raised 4.2 → 5.5 with structured-content (JSON / base64 / CSS) skip-filters that bypass the entropy gate without weakening regex pattern detection. Tunable via `SecurityConfig`.

### Email
- **L25** — Email adapter: IMAP read / search / draft + SMTP send, all gated by trust + confirmation flow.
- **L33b** — Per-invocation IMAP session reuse via `EmailAdapter.imap_session()` async context manager (`ContextVar`-tracked, transparent nesting). New `email_search_and_read` composite tool — single round-trip search + per-id read.

### Reflection & style
- **L26** — Reflection loop (three-pass: pattern mining → proposal generation → queue write) with `hestia reflection` CLI lifecycle controls.
- **L27** — Style profile (per-user interaction-style learning that never mutates identity).

### Bug fixes & hardening
- **L28** — `nh3` replaces unmaintained `bleach`; `read_artifact` registered in CLI; new `delete_memory` tool; deterministic `Message-ID` generation; IMAP search query injection hardened.
- **L29** — Scheduler failure visibility (last-N errors surfaced via `hestia reflection status` / `hestia style show`); missing-file warnings for SOUL.md and calibration.json; env-var-first secrets hygiene; ADRs consolidated under a single `docs/adr/`.
- **`hestia style disable`** no longer crashes at invocation; the command
  is now a proper Click signature with accurate docstring (L35a).
- **`hestia policy show`** now reflects the live tool registry, the active
  `PolicyConfig.delegation_keywords`, the active retry policy, and the
  trust preset name — instead of hand-written strings that drifted (L35b).
- **`ContextBuilder._join_overhead`** is now computed lazily once and cached
  across builds, completing the L32c tokenize-cache work (L35a).
- **TOCTOU-safe `get_or_create_session`** — the prior SELECT-then-INSERT
  pair could create duplicate ACTIVE rows for the same
  `(platform, platform_user)` under concurrent first-message arrival
  (e.g. two Telegram updates polled in the same tick). Symptoms included
  split message history and scheduler tasks attached to the "wrong"
  session. Fixed by adding partial unique index `ux_sessions_active_user`
  on `sessions(platform, platform_user) WHERE state = 'active'` and
  rewriting the method as a dialect-aware
  `INSERT … ON CONFLICT DO NOTHING` upsert. The matching contract is now
  enforced for `create_session(archive_previous=None)` as well — both
  production callers (`/reset` and the subagent factory) were already
  safe. New `tests/unit/test_sessions_race.py` covers the 20-coroutine
  storm. Pre-tag hotfix; ships *in* `v0.8.0`. Idempotent runtime
  migration in `src/hestia/persistence/migrations/` upgrades existing
  databases on next bootstrap.

### Skills & polish
- **L33c** — Skills framework gated behind `HESTIA_EXPERIMENTAL_SKILLS=1` (raises `ExperimentalFeatureError` otherwise — visibility > convenience for a public release). ADR-0022. `_format_datetime` hoisted to module scope. `DefaultPolicyEngine.should_delegate` keyword list exposed via `PolicyConfig.delegation_keywords`. Matrix `_extract_in_reply_to` schema-validation contract locked with regression tests.
- **L34** — Public-release polish: README model recommendations table (Llama-3.1-8B Q4_K_M default), "Running Hestia as a daemon" section, demo placeholder, env-var-first email setup guide.

### New diagnostic commands

- **`hestia doctor`** — read-only nine-check health snapshot covering Python
  version, dependency sync, config load, SQLite integrity, llama.cpp
  reachability, platform prerequisites, trust preset, and memory epoch.
  Use as the first step in any "it stopped working" investigation. (L35c)

### Upgrade docs

- **`UPGRADE.md`** — hand-checked v0.2.2 → v0.8.0 upgrade checklist for
  the early cloners. Documents required new config sections (`trust`,
  `web_search`, `security`, `style`, `reflection`), the `bleach` → `nh3`
  swap, and the recommended `hestia doctor` verification step. (L35d)

### Refactoring

Three loops landed after the L35d snapshot but ahead of the public tag.
None change behavior; all tighten internals so the v0.8.1+ feature work
(voice adapter, Copilot cleanup backlog) starts from a smaller, more
maintainable surface.

- **L36** — `app.py` decomposition: every `_cmd_*` async/sync function
  moved verbatim into a new `src/hestia/commands.py` module. `app.py`
  shrank from **1,533 → 517 lines (-66%)** and now hosts only
  infrastructure (`CliAppContext`, `make_app`, `run_async`,
  `CliResponseHandler`, meta-command dispatch). `cli.py`'s
  `from hestia.app import _cmd_*` block is now `from hestia.commands`.
  Tests unchanged: 778 passed, 6 skipped.
- **L37** — Code cleanup sweep: removed dead `hasattr()` probes on typed
  dataclasses inside `_build_failure_bundle` (engine.py); deleted the
  no-op `app = app if isinstance(app, CliAppContext) else app` in
  `run_platform`; fixed `_cmd_schedule_add` over-indent; hoisted
  `schedule_disable`, `schedule_remove`, and `init` from inline `cli.py`
  bodies into proper `_cmd_*` delegations in `commands.py`. Ruff
  baseline crunched **43 → 23** with 20 real fixes (no `# noqa`
  introduced).
- **L38** — Delegation keyword consolidation: split into two named
  constants (`DEFAULT_DELEGATION_KEYWORDS` for explicit triggers like
  `delegate`, `subagent`, `spawn task`; `DEFAULT_RESEARCH_KEYWORDS` for
  `research`, `investigate`, `analyze deeply`, `comprehensive`), each
  driven by its own `PolicyConfig` field with module-constant fallback.
  `_cmd_policy_show` now displays both lists with accurate labels — the
  L33c-introduced misnaming (research keywords surfaced under
  "delegation" label) is fully resolved. **Config break footnote:**
  anyone who customized `PolicyConfig.delegation_keywords` since L33c
  was actually overriding research triggers; for research overrides
  going forward, set `PolicyConfig.research_keywords` instead.

### Known issues — deferred to v0.8.1+

The following non-blocking findings from the public Copilot review have
been triaged into a backlog (`docs/development-process/kimi-loops/L40-copilot-cleanup-backlog.md`)
and will land on feature branches before the next release prep merges
them to `develop`:

- **Sequential tool dispatch.** When the model emits multiple tool calls
  in one assistant turn, the orchestrator dispatches them sequentially
  even when they have no inter-call dependency (e.g. `search_memory` +
  `web_search`). Concurrent dispatch is a single
  `asyncio.gather` away but needs a correctness pass on tool-result
  ordering, confirmation flow, and trace rendering before shipping.
- **`SlotManager.should_evict_slot` is a stub** that always returns
  `False`. Slot eviction policy is currently "hold until process exit"
  — fine for the personal-assistant target but reviewers will flag it.
- **`should_delegate` `for_trust` identity comparison.** The trust check
  uses `if for_trust is TrustLevel.HIGH` rather than `==`. Works today
  because the enum is module-singleton, but future deserialization
  (e.g. loading from a JSON config) would silently miss it.
- **Bare `except:` in two `EmailAdapter` recovery paths.** Should narrow
  to `(IMAPException, ConnectionError, OSError)`.
- **`prompt_on_mobile` docstring drift** — the doc claims the call
  blocks until confirmation, but the implementation is fire-and-forget
  via the platform's confirm callback.
- **Open `# TODO(L*)` markers.** Three low-impact ones remain in
  `engine.py`, `slot_manager.py`, and `style/builder.py`. Backlog spec
  enumerates each with the original loop reference.

These will be addressed on `feature/copilot-cleanup-*` branches per the
post-release merge discipline rule in `.cursorrules` — no merge to
`develop` until a `v0.8.1` release-prep document names them.

### Stats
- **783 tests** passing across unit + integration (was 250-ish at v0.2.2).
- **0 mypy errors** in `src/hestia/`.
- **228 ruff errors** in `src/` and `tests/` combined; **23 in `src/`
  alone** (the L37 baseline). Was uncapped at v0.2.2.
- **22 ADRs** capturing every architectural decision (ADR-0014 through
  ADR-0022).
- **18 Kimi loops** (L20 → L38), with the L29-L31 monolithic loops
  manually finished by Cursor; L32a-L33c, L35a-d, and the L36-L38
  overnight chain all executed cleanly under the mini-loop chunking
  strategy. The TOCTOU hotfix landed in-process by Cursor (no Kimi
  loop) on `feature/hotfix-session-race`.

## [0.7.12] — 2026-04-18

### Changed
- **README model recommendations.** New "Recommended models" table under "Running on your hardware" with concrete GGUF picks (Llama-3.1-8B Q4_K_M, Qwen 2.5 7B Q4_K_M, Llama-3.2-3B Q5_K_M, Qwen 2.5 14B Q4_K_M) and quantization guidance.
- **README deployment section expanded.** New "Running Hestia as a daemon" section documents all unit files in `deploy/`, shows systemd enable/start sequences, and cross-links env-var configuration (`HESTIA_SOUL_PATH`, `HESTIA_CALIBRATION_PATH`, `HESTIA_EXPERIMENTAL_SKILLS`, `EMAIL_APP_PASSWORD`).
- **Email setup guide rewritten.** Env-var workflow (`password_env`) is now the unequivocal primary path; plaintext `password=` example is demoted to an "ephemeral testing only" callout. Added design-rationale references to L25 handoff and L29 ADR consolidation.

### Added
- README "Demo" placeholder with asciinema link placeholder, screenshot path placeholder, and a short text transcript.
- Unreleased "Towards 0.8.0" preface block summarizing the L20–L34 feature arc.

## [0.7.11] — 2026-04-18

### Changed
- **Skills experimental feature flag (L33c).** The `@skill` decorator and `hestia skill *` CLI commands now require `HESTIA_EXPERIMENTAL_SKILLS=1`. Without it, users get a clear `ExperimentalFeatureError` instead of silent no-op behavior.
- **Policy engine keyword extraction tunable.** `DefaultPolicyEngine.should_delegate` now reads research keywords from `PolicyConfig.delegation_keywords` (defaults to `DEFAULT_DELEGATION_KEYWORDS`). Setting `delegation_keywords=()` disables keyword-based delegation entirely.
- `_format_datetime` hoisted from closure inside `_cmd_schedule_show` to module scope in `src/hestia/app.py`.

### Added
- `ExperimentalFeatureError` exception type in `src/hestia/errors.py`.
- `PolicyConfig` dataclass with `delegation_keywords` field.
- ADR-0022 documenting the skills preview feature-flag decision.
- `tests/unit/test_skills_feature_flag.py` — regression coverage for the flag gate.
- `tests/unit/test_policy_delegation_keywords.py` — regression coverage for custom and empty keyword configs.
- `tests/unit/test_matrix_adapter.py` — regression coverage for `_extract_in_reply_to` schema validation contract.

## [0.7.10] — 2026-04-18

### Changed
- **EmailAdapter per-invocation IMAP session reuse (L33b).** Added `imap_session()` async context manager with `ContextVar`-based connection reuse. Every per-method IMAP call (`list_messages`, `read_message`, `search_messages`, `create_draft`, `move_message`, `flag_message`, `send_draft`) now routes through `imap_session()`; when nested inside an outer `async with adapter.imap_session():`, inner calls automatically reuse the same `IMAP4_SSL` connection. Standalone calls remain backward-compatible (each opens and closes its own session). SMTP send is unchanged.

### Added
- `email_search_and_read` composite tool — searches messages and reads the top *N* matches in a single IMAP round trip, demonstrating the session-reuse pattern.
- `tests/unit/test_email_session_reuse.py` — asserts single-connection reuse, proper cleanup on exception, nested-session deduplication, and standalone per-method isolation.
- `tests/integration/test_email_search_and_read.py` — end-to-end composite tool coverage with mocked IMAP.

## [0.7.9] — 2026-04-18

### Changed
- **Behavior change:** Default `InjectionScanner.entropy_threshold` raised from 4.2 to 5.5, and structured content (JSON / base64 / CSS) now skips the entropy gate while still running the regex pattern check. This dramatically reduces false-positive annotations on tool outputs. Tunable via `SecurityConfig.injection_entropy_threshold` and `SecurityConfig.injection_skip_filters_for_structured`.

### Added
- `tests/unit/test_injection_scanner_tuning.py` — regression coverage for the new structured-content filters and threshold change.

## [0.7.8] — 2026-04-18

### Changed
- **ContextBuilder per-message `/tokenize` cache (L32c).** The trim loop
  previously issued O(N) HTTP calls per build — one round trip per candidate
  message.  Per-message token counts are now cached (keyed on
  `(role, content)`) for the lifetime of the builder instance.  A constant
  join-overhead approximation replaces the concatenated-string tokenization
  in the loop, reducing amortized tokenize calls to O(1) per build for
  unchanged messages.  Protected and final counts still use the full
  `count_request` path for accuracy.

### Added
- `tests/unit/test_context_builder_tokenize_cache.py` — asserts cache hits
  across repeated builds, one-call invalidation on new messages, parity
  with the old joined-string baseline (±1 message at the boundary), and
  that `(role, content)` is the cache key (not `created_at`).
- ADR-0021 documenting both the L32b prefix-layer registry and the L32c
  tokenize cache.

## [0.7.7] — 2026-04-18

### Changed
- **ContextBuilder prefix-layer registry (L32b).** Replaced the four optional
  `*_prefix` kwargs on `ContextBuilder.build()` with a private `_PrefixLayer`
  registry. Assembly order (`identity → memory_epoch → skill_index → style →
  system_prompt`) is now data, not code; adding a fifth layer in a future loop
  will require only one line in `_prefix_layers()` and one setter. No real call
  site used the per-call kwargs — the orchestrator already relied on setters.

### Added
- `tests/unit/test_context_builder_prefix_registry.py` — asserts documented
  layer order, skipped-layer behaviour, fall-through to bare system prompt, and
  that `build()` no longer accepts prefix kwargs.

## [0.7.6] — 2026-04-18

### Changed
- **Dead-code removal (L32a).** Deleted unused `TurnState` enum and `ToolResult`
  dataclass from `src/hestia/core/types.py`. The orchestrator already maintains
  its own `TurnState` in `src/hestia/orchestrator/types.py`; the duplicate in
  `core/types.py` was a booby trap for future contributors. `ToolResult` was
  never imported anywhere — the codebase uses `Message(role="tool", ...)`.

### Added
- Regression test module:
  - `tests/unit/test_core_types_dead_code_removed.py` — asserts that
    `TurnState`, `TERMINAL_STATES`, and `ToolResult` are absent from
    `hestia.core.types` and that the orchestrator's `TurnState` still exists.

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
