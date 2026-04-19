# Kimi — current task (orchestration pointer)

**Orchestrator:** Cursor updates this file after each review.

**Last set by:** Kimi — 2026-04-19 (L42 complete on feature branch; launching L43)

---

## Current task

**Status:** **IDLE** — L43 blocked on missing Dylan-side prereqs.

**Blocked on:**

1. **Dedicated phone number** for the Hestia userbot (prepaid SIM recommended).
2. **Telegram API application** registered at my.telegram.org/apps using that
   number. Note `api_id` and `api_hash`.
3. **`py-tgcalls` build verified** on the Ubuntu box (`pip install pytgcalls` in
   the Hestia venv; may need `libssl-dev libavcodec-dev libavformat-dev`).
4. **Piper voice file** downloaded to `~/.cache/hestia/voice/` (e.g.
   `en_US-amy-medium.onnx` + `.onnx.json`).
5. Dylan's **Telegram `user_id`** (for `allowed_caller_user_ids`).

**Verification on disk (2026-04-19):**

- `pyrogram` — **not installed** in `.venv`
- `py-tgcalls` — **not installed** in `.venv`
- Piper voice files — **not present** in `~/.cache/hestia/voice/`
- Telegram API credentials — **not found** in `.matrix.secrets.py` or config

**What to do when prereqs are ready:**

1. Install/build pyrogram + py-tgcalls in `.venv`.
2. Place Piper voice files.
3. Provide `api_id`, `api_hash`, and `allowed_caller_user_ids` to Kimi.
4. Reset KIMI_CURRENT from IDLE back to L43 active.
5. Create `feature/voice-phase-b-calls` from `feature/voice-shared-infra` and run loop.

---

## Completed loops (reference)

**L42 completion snapshot:**

- Branch: `feature/voice-phase-a-messages` (pushed to `origin/feature/voice-phase-a-messages`)
- Implementation commits: `de5f8db` (config), `583b6c5` (handler), `1f1a9a7` (tests), `de31bb2` (docs + cleanup)
- Orchestration docs commit on branch: `ac4c196` (handoff + KIMI_CURRENT + loop log)
- `.kimi-done`: `LOOP=L42`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=23`, `TESTS=810 passed, 12 skipped`
- Merge status: **NOT merged to `develop`** (correct per post-release merge discipline)

**L41 completion snapshot:**

- Branch: `feature/voice-shared-infra` (pushed to `origin/feature/voice-shared-infra`)
- Implementation commits: `3e83e25` (pipeline), `191a0b4` (VAD + config), `5ef6c41` (pyproject + doctor + guide), `bb06e00` (tests)
- Orchestration docs commit on branch: `779e369` (handoff + KIMI_CURRENT + loop log)
- `.kimi-done`: `LOOP=L41`, `MYPY_FINAL_ERRORS=0`, `RUFF_SRC=23`, `TESTS=798 passed, 6 skipped`
- Merge status: **NOT merged to `develop`** (correct per post-release merge discipline)

**Important:** per `.cursorrules` post-release merge discipline, **do not merge
L41 or L42 to `develop` yet**. Push feature branches only; merge waits for a v0.8.1+
release-prep doc naming the branches in scope.

**State on disk:**

- Develop tip: `b1e81ae` (v0.8.0 tag). Unchanged since L41 branched.
- `feature/voice-shared-infra` tip: `bb06e00` + orchestration commit(s).
- `feature/voice-phase-a-messages` tip: `ac4c196`.
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
- **L42** — complete on `origin/feature/voice-phase-a-messages` (`de5f8db` … `ac4c196`);
  waiting for v0.8.1+ release-prep before merge to `develop`.
- **L43** — `docs/development-process/kimi-loops/L43-voice-phase-b-calls.md`
  on `feature/voice-phase-b-calls` (forks from `feature/voice-shared-infra`)
  — Pyrogram userbot, py-tgcalls integration, half-duplex first then
  barge-in, `hestia setup telegram-voice` CLI, ADR-0024 documenting the
  two-account model. **ACTIVE NOW.**

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
