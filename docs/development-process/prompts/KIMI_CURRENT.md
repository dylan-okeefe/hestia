# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Kimi — 2026-04-19 (L41 complete on feature branch; launching L42)

---

## Current task

**Active loop:** **L42** — `docs/development-process/kimi-loops/L42-voice-phase-a-messages.md`
on `feature/voice-phase-a-messages` (forks from `feature/voice-shared-infra`).

**L41 completion snapshot:**

- Branch: `feature/voice-shared-infra` (pushed to `origin/feature/voice-shared-infra`)
- Implementation commits: `3e83e25` (pipeline), `191a0b4` (VAD + config), `5ef6c41` (pyproject + doctor + guide), `bb06e00` (tests)
- Orchestration docs commit on branch: *(pending — handoff + KIMI_CURRENT + loop log)*
- `.kimi-done`: `LOOP=L41`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=23`, `TESTS=798 passed, 6 skipped`
- Merge status: **NOT merged to `develop`** (correct per post-release merge discipline)

**Launch sequence now (L42):**

1. Create `feature/voice-phase-a-messages` from `feature/voice-shared-infra`.
2. Run `./scripts/kimi-run-current.sh`.
3. Wait for valid `.kimi-done` (`HESTIA_KIMI_DONE=1`, `LOOP=L42`).
4. Review diffs + run gates (`pytest`, `mypy src/hestia`, `ruff check src/`).
5. Fix/tighten prompt and rerun L42 if red.
6. When green: push `feature/voice-phase-a-messages` to origin, write loop log entry, and
   advance this file to L43.

**Important:** per `.cursorrules` post-release merge discipline, **do not merge
L41 or L42 to `develop` yet**. Push feature branches only; merge waits for a v0.8.1+
release-prep doc naming the branches in scope.

**State on disk:**

- Develop tip: `b1e81ae` (v0.8.0 tag). Unchanged since L41 branched.
- `feature/voice-shared-infra` tip: `bb06e00` + orchestration commit(s).
- Main tip: `5155917` (v0.8.0 release merge).
- Tag `v0.8.0` at `b1e81ae`.

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

- **L40** — complete on `origin/feature/l40-copilot-cleanup` (`d604313` + `b0c4668`);
  waiting for v0.8.1+ release-prep before merge to `develop`.

### Track 5 — Voice adapter arc

Three loops, two phases, build on shared infrastructure:

- **L41** — complete on `origin/feature/voice-shared-infra` (`3e83e25` … `bb06e00`);
  waiting for v0.8.1+ release-prep before merge to `develop`.
- **L42** — `docs/development-process/kimi-loops/L42-voice-phase-a-messages.md`
  on `feature/voice-phase-a-messages` (forks from `feature/voice-shared-infra`)
  — Telegram bot voice-message handler, integration test with mocked Telegram.
  **ACTIVE NOW.**
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
