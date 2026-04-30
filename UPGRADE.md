# Upgrading Hestia

This guide covers upgrading between recent releases. Read each step before running it.

If you are on a version older than v0.2.2, upgrade to v0.2.2 first
(see the v0.2.2 release notes), then follow the sections below in order.

There is no automated migration tool yet (`hestia upgrade` is planned but not in v0.10.0).

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
trust, see `docs/guides/trust-config.md`.

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
read `docs/guides/reflection-setup.md`.

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
- `hestia skills *` (L33c) — only useful with `HESTIA_EXPERIMENTAL_SKILLS=1`.
- `hestia reflection *` (L26) — only useful with `reflection.enabled: true`.
- `hestia style *` (L27)
- `hestia memory epochs *` (refined across the arc)

## 6. Verify

```bash
hestia doctor
```

All checks should be `✓` (or `[ok]` with `--plain`). If any are `✗`,
read the detail line and fix before proceeding. Common fixes:

- "uv pip check" failures → `uv sync` again.
- llama.cpp not reachable → start the llama.cpp server (see deploy/ in the repo).
- Memory epoch unparseable → see `docs/guides/memory-epochs.md`.

## 7. First run after upgrade

```bash
hestia memory epochs list
hestia chat
```

If memory loads and chat starts, you're upgraded.

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
