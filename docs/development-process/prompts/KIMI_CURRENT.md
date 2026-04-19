# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Kimi — 2026-04-19 (L40 complete; advancing to L41 voice shared infra)

---

## Current task

**Active loop:** **L41** — `docs/development-process/kimi-loops/L41-voice-shared-infra.md`
on feature branch `feature/voice-shared-infra`.

**Launch sequence now:**

1. Create/switch to the L41 feature branch from `develop`.
2. Run `./scripts/kimi-run-current.sh`.
3. Wait for valid `.kimi-done` (`HESTIA_KIMI_DONE=1`, `LOOP=L41`).
4. Review diffs + run gates (`pytest`, `mypy src/hestia`, `ruff check src/`).
5. Fix/tighten prompt and rerun L41 if red.
6. When green: push `feature/voice-shared-infra` to origin, write loop log entry, and
   advance this file to L42.

**Important:** per `.cursorrules` post-release merge discipline, **do not merge
L41 to `develop` yet**. Push feature branch only; merge waits for a v0.8.1+
release-prep doc naming the branch in scope.

**State on disk:**

- Develop tip: `b1e81ae` ("chore(release): pyproject.toml 0.8.1.dev2 -> 0.8.0; uv.lock regen"). Includes the L36-L38 overnight merges, the voice-call-setup planning docs merge, the `.cursorrules` post-release merge discipline rule, and the `feature/hotfix-session-race` TOCTOU fix. ~40 commits ahead of `origin/develop` at the time of writing.
- Main tip: `5155917` ("Merge develop into main for v0.8.0 release"). Was at `255dc2b` (`v0.2.2`) before the merge — a `--no-ff` was required because main carried a no-op release-merge commit that made FF impossible.
- Tag `v0.8.0` annotated at `b1e81ae` (the version-bump commit on develop, intentionally chosen so future patch releases branch from a develop-history ancestor without picking up main-only merge commits).
- L40 branch: `feature/l40-copilot-cleanup` at `d604313` — 796 passed, 6 skipped; mypy 0; ruff 23 (unchanged). **Not merged to develop.**

---

## Post-release policy state — important for the next agent

The `.cursorrules` rule added in this release (see "Post-release merge
discipline" section) **forbids merging feature branches to `develop`**
after the v0.8.0 tag until a release-prep doc names the upcoming version.

**What this means concretely:**

- Kimi may run loops on feature branches at any time.
- **Cursor must NOT merge those branches to `develop`** until a
  `docs/development-process/prompts/v0.8.1*.md` (or similar) exists
  listing the loops in the v0.8.1 scope.
- Voice arc and Copilot cleanup work is queued as feature branches only;
  the spec files explicitly mark "do NOT merge to develop yet".

The exception list (planning docs, ADRs, .cursorrules updates) is
documented in the rule itself.

---

## Queued — feature branch work (do NOT merge to develop until release-prep)

Each of these is a complete spec ready for Kimi. Branch is named in the
spec; landed work stays on the feature branch and pushes to `origin/<branch>`.
**Merge to `develop` happens only when a v0.8.1 (or later) release-prep
doc names the branch in its scope.**

### Track 4 — Copilot cleanup backlog

- ~~**L40** — `docs/development-process/kimi-loops/L40-copilot-cleanup-backlog.md`~~ **DONE**
  — branch `feature/l40-copilot-cleanup` at `d604313`. All six items + TODOs
  resolved. Not merged to develop.

### Track 5 — Voice adapter arc

Three loops, two phases, build on shared infrastructure:

- **L41** — `docs/development-process/kimi-loops/L41-voice-shared-infra.md`
  on `feature/voice-shared-infra` — STT/TTS pipeline, VAD wrapper,
  VoiceConfig, `hestia[voice]` extra, voice-setup.md, unit tests with
  mocked models.
- **L42** — `docs/development-process/kimi-loops/L42-voice-phase-a-messages.md`
  on `feature/voice-phase-a-messages` (forks from `feature/voice-shared-infra`)
  — Telegram bot voice-message handler, integration test with mocked Telegram.
- **L43** — `docs/development-process/kimi-loops/L43-voice-phase-b-calls.md`
  on `feature/voice-phase-b-calls` (forks from `feature/voice-shared-infra`)
  — Pyrogram userbot, py-tgcalls integration, half-duplex first then
  barge-in, `hestia setup telegram-voice` CLI, ADR-0024 documenting the
  two-account model.

### Deferred (pre-existing backlog, no specs yet)

- **L39** — `hestia upgrade` command (auto-fix what `hestia doctor` flags).
- **L44** — Dogfooding journal rollup after a week of real v0.8.0 use.

---

## Reference

- Queue: [`../kimi-phase-queue.md`](../kimi-phase-queue.md)
- Launch plan: [`v0.8.0-release-and-voice-launch.md`](v0.8.0-release-and-voice-launch.md)
- Pre-release plan (historical): [`../reviews/v0.8.0-pre-release-plan.md`](../reviews/v0.8.0-pre-release-plan.md)
- Loop log: [`../kimi-loop-log.md`](../kimi-loop-log.md)
- Post-release merge discipline rule: `.cursorrules` (added 2026-04-19)
