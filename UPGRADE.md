# Upgrading Hestia

This guide covers upgrading between recent releases. Read each step before running it.

If you are on a version older than v0.2.2, upgrade to v0.2.2 first
(see the v0.2.2 release notes), then follow the sections below in order.

There is no automated migration tool yet; a future upgrade subcommand is planned
but not implemented as of v0.10.0.

> **Migration model:** Hestia bootstraps its database with `create_tables()` plus
> idempotent runtime migrations on every startup. The Alembic files under
> `migrations/` exist for reference and development convenience, but they are
> **not** the production upgrade path. Running `hestia init` is sufficient.

---

## v0.16.0

**Released:** 2026-08-24  
**Full notes:** [`CHANGELOG.md`](CHANGELOG.md) and
[`docs/releases/v0.16.0.md`](docs/releases/v0.16.0.md)

A large release with **three breaking changes**: workflow authorization is
now allowlist-only (every workflow must be re-activated once), terminal
commands run with a restricted environment, and direct registry callers
must pass a `ToolCallContext`. Back up before upgrading.

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

(Adjust the path to wherever your `storage.database_url` points.)

### 2. Pull and sync

```bash
git fetch --tags
git checkout v0.16.0
uv sync --all-extras
```

### 3. Schema changes (applied automatically)

Startup runs `create_tables()` plus idempotent runtime migrations. This
release adds two:

- **m010** adds an `is_test` flag to `workflow_executions` so test runs are
  excluded from aggregates.
- **m011** backfills `workflows.allow_listed_tools` from each workflow's
  active version. It only touches workflows whose stored grant is still the
  empty default; custom grants are never overwritten.

No manual migration is needed; `hestia init` or a normal startup applies
them.

### 4. Re-activate every workflow once (breaking)

Workflow tool access is now allowlist-only: a workflow may invoke exactly
the tools its activated version grants (see
[ADR-052](docs/adr/ADR-052-allowlist-only-tool-authorization-for-unattended-channels.md)).
Migration m011 pre-populates each grant from the active version, so in most
cases you only need to confirm:

1. Open each workflow in the web dashboard (or activate via the API).
2. Activate its current version.
3. If an authorization diff appears, review the added/removed tools and
   confirm.

Workflows with no active version get no grant; activate a version and
confirm its diff before they can run tools. Activating a version whose
grant changed now returns HTTP 409 until you pass
`?confirm_allow_list_change=true` (the web UI shows a dialog).

### 5. Check terminal commands that relied on inherited env (breaking)

`terminal` child processes now receive only `PATH`, `HOME`, `USER`,
`LOGNAME`, `SHELL`, `TERM`, `TMPDIR`, `LANG`, and `LANGUAGE`. Commands
that depended on other environment variables — API keys exported in your
shell, virtualenv activation, tool-specific config vars — will no longer
see them. Move anything a workflow needs into its node arguments or a
credentials file the command reads explicitly.

### 6. Update external tool modules for ToolCallContext (breaking)

If you registered tools through `extra_tool_modules` or call
`ToolRegistry.call()` directly: calls now require a `ToolCallContext`, and
a registry without a bound capability gate refuses all calls. See
[ADR-052](docs/adr/ADR-052-allowlist-only-tool-authorization-for-unattended-channels.md).
Tools invoked through normal chat and workflow dispatch need no changes.

### 7. Restart services

```bash
systemctl --user restart hestia-serve.service
```

### 8. Heads-up

- Streaming turns now fail fast on inference stalls instead of delivering
  truncated answers; retries apply to non-streaming turns only.
- The web dashboard on an exposed interface now refuses insecure startup
  combinations (auth disabled, debug login, wildcard auto-approval).
- `SOUL.md` is no longer tracked in git; copy `SOUL.example.md` if you are
  setting up fresh. Your existing file is untouched.
- If you maintain out-of-tree imports of `hestia.persistence.sessions`,
  migrate to the split stores (`session_store` / `message_store` /
  `turn_store`); the deprecated facade will be removed in a future release.

---

## v0.15.1

**Released:** 2026-06-24  
**Full notes:** [`CHANGELOG.md`](CHANGELOG.md)

A small patch release. No schema migrations are required; pull, sync, and
restart.

### 1. Pull and sync

```bash
git fetch --tags
git checkout v0.15.1
uv sync --all-extras
```

### 2. Restart services

```bash
systemctl --user restart hestia-serve.service
```

## v0.15.0

**Released:** 2026-06-22  
**Full notes:** [`CHANGELOG.md`](CHANGELOG.md)

A large release (foundation work plus new subsystems). Because it adds several
tables and columns at once, back up and verify the upgrade on a copy of your
runtime database before pointing your live instance at it.

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

### 2. Schema changes (applied automatically)

Startup runs `create_tables()` plus idempotent runtime migrations. This release
adds soft-delete and protected-set columns plus the maintenance trace table for
memory maintenance, the compaction-archive table, the `correction` column on
`messages`, and the split session/message/turn stores. No manual migration is
needed; `hestia init` or a normal startup applies them.

### 3. Enable overnight memory maintenance (optional)

```bash
hestia memory-maintenance ensure-tasks
```

Registers the nightly deterministic and weekly LLM maintenance passes. Undo any
action with `hestia memory maintenance undo <action-id>`.

### 4. Heads-up

- The unified `CapabilityGate` now enforces per-user trust and gates destructive
  tools on unattended and injection-flagged paths. Review your trust config and
  any per-user presets after upgrading.
- New `/compact` meta-command compacts the current session in place.
- `persistence/sessions.py` is now a deprecated re-export facade and will be
  removed in v0.16.0; update any external imports to the split stores.

## v0.14.0

**Released:** 2026-06-15  
**Full notes:** [`CHANGELOG.md`](CHANGELOG.md)

If you are upgrading from v0.13.1 or earlier, follow the previous sections first,
then continue here.

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

### 2. Pull and sync

```bash
git fetch --tags
git checkout v0.14.0
uv sync --all-extras
```

### 3. No manual migrations required

v0.14.0 adds only runtime-hardening and tooling changes. Start `hestia` normally;
`create_tables()` and idempotent runtime migrations will handle the database.

---

## v0.12.2

**Released:** 2026-05-27  
**Full notes:** [`docs/releases/v0.12.2.md`](docs/releases/v0.12.2.md)

If you are upgrading from v0.10.0 or earlier, follow the previous sections first,
then continue here.

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

### 2. Pull and sync

```bash
git fetch --tags
git checkout v0.12.2
uv sync --all-extras
```

### 3. Database migrations

Automatic. `hestia init` runs `create_tables()` and runtime migrations; no Alembic
step is required.

### 4. Config changes

No required config changes for v0.12.2. New optional features:

- Job-alert workflow reliability improvements are automatic.
- `scripts/warmup_site_session.py` can pre-warm Cloudflare-protected sites.
- `scripts/test_workflow_email.py` can test job email workflows against a specific
  IMAP UID.

### 5. Verify

```bash
hestia doctor
hestia chat
```

### What changed (high level)

v0.12.2 is a job workflow reliability patch. It fixes artifact passing, URL
extraction, browser anti-detection, and Cloudflare session management for job
alert processing.

---

## v0.12.2 → v0.13.0

**Released:** 2026-06-06  
**Full notes:** [`docs/releases/v0.13.0.md`](docs/releases/v0.13.0.md)

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

### 2. Pull and sync

```bash
git fetch --tags
git checkout v0.13.0
uv sync --all-extras
```

### 3. Database migrations

Automatic. `hestia init` runs `create_tables()` and runtime migrations; no Alembic
step is required.

### 4. Config changes

No required config changes for v0.13.0. New features are opt-in:

- Browser sessions dashboard and CDP screencast streaming require `browser.enabled: true`
  (or Playwright installed) and `web.enabled: true` for the dashboard.
- Visual workflow editor improvements are available automatically when workflows
  are enabled.
- New built-in tools (`edit_file`, `glob`, `grep`, `rollback_turn`) are available
  automatically when the tool registry is built.

### 5. Verify

```bash
hestia doctor
hestia chat
```

### What changed (high level)

v0.13.0 ships persistent browser session management, CDP/headed browser streaming,
playwright-stealth anti-detection, email-triggered workflows, and new built-in
tools (`edit_file`, `glob`, `grep`, `rollback_turn`). The web dashboard adds dark
mode, session titles, debug login, and a shared CSS system.

---

## v0.2.2 → v0.8.0

## 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

## 2. Pull and sync

```bash
git fetch --tags
git checkout v0.8.0
uv sync
```

## 3. Required config additions

For each of the new top-level sections introduced between v0.2.2 and v0.8.0,
the following YAML preserves v0.2.2 behavior. You can paste these into your
existing config; `uv sync` does not write config files.

### `trust:` (introduced L20)

Default in v0.8.0 is `paranoid` — every external action requires confirmation.
To match v0.2.2 (no trust gating), use `permissive`. To opt in to gradual
trust, see `docs/guides/security.md`.

```yaml
trust:
  preset: paranoid  # paranoid | balanced | permissive
```

### `web_search:` (introduced L20)

Disabled by default. To enable, set provider and supply a Tavily API key.

```yaml
web_search:
  provider: ""  # "" disables web search; "tavily" enables it
```

### `security:` (introduced L24, tuned L33a)

Prompt-injection scanner; default threshold 5.5.

```yaml
security:
  injection_scanner:
    enabled: true
    entropy_threshold: 5.5
```

### `style:` (introduced L27)

Style profile that learns from user messages.

```yaml
style:
  enabled: true
```

### `reflection:` (introduced L26)

Background reflection loop; **off by default**. Enable only if you've
read `docs/guides/reflection-tuning.md`.

```yaml
reflection:
  enabled: false
```

### `skills:` (preview, gated)

Skills are an experimental preview. They are inert unless you set
`HESTIA_EXPERIMENTAL_SKILLS=1` in your environment. No config changes needed.

## 4. Dependency changes

- `bleach` removed; replaced by `nh3` (Rust-backed). `uv sync` handles this.
  If you forked Hestia and imported `bleach` directly, migrate to `nh3`.
- All other dependency changes are additive and `uv sync` is sufficient.

## 5. CLI changes

`cli.py` was decomposed into `app.py` + `platforms/runners.py` + `bootstrap.py`
during L30. **User-facing commands are unchanged.** If you wrote scripts that
imported internal modules from `hestia.cli`, those imports may have moved.

New commands in v0.8.0:

- `hestia doctor` (L35c) — read-only health check. Run this in step 6 below.
- `hestia reflection *` (L26) — only useful with `reflection.enabled: true`.
- `hestia style *` (L27)

## 6. Verify

```bash
hestia doctor
```

All checks should be `✓` (or `[ok]` with `--plain`). If any are `✗`,
read the detail line and fix before proceeding. Common fixes:

- "uv pip check" failures → `uv sync` again.
- llama.cpp not reachable → start the llama.cpp server (see deploy/ in the repo).

## 7. First run after upgrade

```bash
hestia chat
```

If chat starts, you're upgraded.

## What changed (high level)

Between v0.2.2 and v0.8.0, Hestia gained a trust and confirmation ladder
(L20–L23) that gates destructive tools behind explicit user approval on every
platform. The orchestrator now compresses history and emits loud warnings when
context grows too large, rather than silently truncating.

Email, reflection, and style profiles arrived in L24–L27. Email supports
IMAP read/search and SMTP draft/send with app-password hygiene. Reflection
runs a nightly three-pass pipeline that mines patterns and proposes config
changes (never auto-applied). Style learns per-user interaction preferences
without mutating the operator-authored identity.

Critical-bug fixes and reliability work spanned L28–L29: `bleach` was replaced
with `nh3`, IMAP injection is hardened, and missing-file warnings now surface
at startup. Architecture cleanup in L30–L33c decomposed the CLI monolith,
added a prompt-injection scanner with structured-content skip-filters, and
introduced an experimental skills framework gated behind an env flag. The
public-release polish in L34–L35d added README deployment guidance, a
`hestia doctor` diagnostic command, and this upgrade checklist.

---

## v0.8.0 → v0.9.0

**Released:** 2026-04-19  
**Full notes:** [`docs/releases/v0.9.0.md`](docs/releases/v0.9.0.md)

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

### 2. Pull and sync

```bash
git fetch --tags
git checkout v0.9.0
uv sync --all-extras
```

### 3. Database migration (automatic)

v0.9.0 introduces a **one-way FTS5 memory migration** that adds `platform` and
`platform_user` columns to the `memory` table and backfills them from sessions.
It runs automatically on first boot. Rows that cannot be backfilled are
attributed to `__legacy__`; see `docs/guides/multi-user-setup.md` for the admin
helper to reassign them.

### 4. Config changes

**No breaking config changes** for single-user deployments. A v0.8.x config
boots on v0.9.0 with identical behavior.

If you are adding a second user, read `docs/guides/multi-user-setup.md` before
enabling `trust_overrides`.

**New optional fields:**

- `trust_overrides: dict[str, TrustConfig]` — grant different trust profiles
  per identity, keyed `"platform:platform_user"`.
- `TelegramConfig.voice_messages` — default **off**. Set to `True` to enable
  Telegram voice-message support (requires `hestia[voice]` extra; see
  `docs/guides/voice-setup.md`).

### 5. Verify

```bash
hestia doctor
```

All checks should pass. If voice is enabled, `doctor` flags missing
prerequisites (ffmpeg, Piper voice files, Whisper weights).

### What changed (high level)

v0.9.0 ships **multi-user safety** and **voice messages**.

Every turn now propagates `current_platform` and `current_platform_user`
`ContextVar`s so downstream code scopes behavior per caller. Memories are
keyed by `(platform, platform_user)`; users cannot see each other's notes.
Allow-lists support `fnmatch` wildcards and validate format per platform.

Voice messages (Phase A) cover Telegram only: OGG/Opus → PCM → Whisper STT →
orchestrator → Piper TTS → OGG/Opus reply. Discord live voice (Phase B) was
explored and later abandoned.

---

## v0.9.0 → v0.10.0

**Released:** 2026-04-22  
**Full notes:** [`docs/releases/v0.10.0.md`](docs/releases/v0.10.0.md)

### 1. Back up

```bash
cp -r ~/.hestia ~/.hestia-backup-$(date +%Y%m%d)
```

### 2. Pull and sync

```bash
git fetch --tags
git checkout v0.10.0
uv sync --all-extras
```

### 3. Required config changes

**Remove Discord voice if present.** `HestiaConfig` no longer accepts a
`discord_voice` field. If you were experimenting with the Discord live-voice
Phase B feature, delete that key from your `config.py` before starting Hestia.

No other config changes are required.

### 4. Database migrations

None. v0.10.0 does not touch the schema.

### 5. Verify

```bash
hestia doctor
hestia chat
```

### What changed (high level)

v0.10.0 hardens Telegram voice messages (sub-word audio guard rejects
<0.25 s accidental tap-and-release notes) and officially abandons the Discord
live-voice experiment. The STT/TTS pipeline lives on for Telegram voice only.

All architecture decisions were split from a 550-line monolith into 33
individual ADR files (`docs/adr/ADR-001` through `ADR-033`) with consistent
numbering and cross-links.
