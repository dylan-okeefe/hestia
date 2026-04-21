# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Cursor — 2026-04-20 (v0.9.0 released; awaiting v0.9.1 prep
or voice Phase B Discord credentials).

---

## Current task

**Status:** **IDLE — v0.9.0 released.** Awaiting either a v0.9.1 release-prep
doc (to start Copilot backlog work) or Dylan's Discord credentials (to start
voice Phase B). No active Kimi loop.

**Completed (not yet merged):**
- `feature/l50-commands-split` — `commands.py` → `commands/` package refactor.
  Handoff: [`docs/handoffs/L50-commands-split-handoff.md`](../../handoffs/L50-commands-split-handoff.md).
  **Do NOT merge to develop** until release-prep merge sequence.

---

## v0.9.0 release snapshot

- **Tag:** `v0.9.0` (annotated) on `develop` tip.
- **Release-prep doc:** [`v0.9.0-release-prep.md`](v0.9.0-release-prep.md)
  (retroactive; names all seven feature branches merged to develop).
- **Orchestration prompt:** [`v0.9.0-release-and-audit-response.md`](v0.9.0-release-and-audit-response.md).
- **Human release notes:** [`../../releases/v0.9.0.md`](../../releases/v0.9.0.md).
- **CHANGELOG:** `[0.9.0]` entry with `### Pre-release hotfixes` subsection.
- **Seven feature branches merged to develop:**
  1. `feature/l40-copilot-cleanup`
  2. `feature/voice-shared-infra`
  3. `feature/voice-phase-a-messages`
  4. `feature/l45a-trust-identity-plumbing`
  5. `feature/l45b-memory-user-scope-migration`
  6. `feature/l45c-multi-user-docs-and-hardening`
  7. `feature/hotfix-v0.9.0-copilot-critical`

---

## What's queued (not authorized yet)

### Copilot audit backlog → v0.9.1 candidate

- Tracking doc: [`v0.9.1-copilot-backlog.md`](v0.9.1-copilot-backlog.md)
  (~39 findings: 5 remaining high, 13 medium, 8 low, 9 test-gap, 4 architecture).
- Per `.cursorrules` "Post-release merge discipline," nothing in this doc
  merges to develop until a `v0.9.1-release-prep.md` names branches by
  exact `feature/*` name.
- Suggested first loop: **H-5** (reject `model.name == "dummy"` at
  config-load unless `HESTIA_ALLOW_DUMMY_MODEL=1`). Small, self-contained,
  good warm-up.

### Voice Phase B (Discord) → v0.9.1-or-later candidate

- Specified in `v0.8.0-release-and-voice-launch.md` Track 5 Phase B
  (rewritten 2026-04-20 to replace the Telegram MTProto userbot plan).
- **Blocked on Dylan-side prereqs:**
  1. Discord bot token in `~/.hestia/.env` as `HESTIA_DISCORD_TOKEN`.
  2. `guild_id` and `voice_channel_id` for Dylan's private Hestia server.
  3. Allowed-speaker Discord user_ids (Dylan + husband).
  4. Piper voice choice.
- When Dylan is ready, he sends a one-line green-light with those four
  inputs. Cursor writes a v0.9.1 release-prep doc naming the Phase B
  feature branches, gets Dylan's OK, then Kimi starts.

---

## Existing blocked work (unchanged)

- **L43 voice calls (original Telegram MTProto plan)** — superseded by
  voice Phase B Discord plan above. Keep the spec for historical reference
  but don't schedule.

---

## Deferred (pre-existing backlog)

- **L39** — `hestia upgrade` command (auto-fix `hestia doctor` findings).
- **L44** — Dogfooding journal rollup after a week of real v0.8.0 /
  v0.9.0 use.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- v0.9.0 release prep: [`v0.9.0-release-prep.md`](v0.9.0-release-prep.md)
- v0.9.0 orchestration prompt: [`v0.9.0-release-and-audit-response.md`](v0.9.0-release-and-audit-response.md)
- v0.9.0 release notes: [`../../releases/v0.9.0.md`](../../releases/v0.9.0.md)
- v0.9.1 backlog: [`v0.9.1-copilot-backlog.md`](v0.9.1-copilot-backlog.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Post-release merge discipline: `.cursorrules`
