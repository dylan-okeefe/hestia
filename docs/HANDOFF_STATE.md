# Hestia — Review & Orchestration State

> **Purpose:** This file is the handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase. Whichever tool picks up the work reads this file first to understand where we are. Whoever finishes a review session updates it.
>
> **Last updated:** 2026-04-10
> **Last updated by:** Claude (Cowork)

---

## Current Branch & Phase

- **Active branch:** `feature/phase-3-telegram`
- **Phase:** 3 — Telegram Adapter
- **Status:** Review complete. 5 bugs found. Ready to merge once bugs are folded into Phase 4 §0.

---

## Review Verdict: Phase 3

**Overall: green to merge** with 5 findings for Phase 4 §0 cleanup.

### Bug 1: Alembic migration STILL missing `scheduled_tasks` (carry-over from Phase 2c)

The Phase 3 prompt §0 explicitly asked for Fix 1: regenerate the initial Alembic migration to include all 5 tables. This was not done. `migrations/versions/ef029058c686_initial_schema.py` still has only 4 tables (sessions, messages, turns, turn_transitions). The `scheduled_tasks` table is absent. A fresh `alembic upgrade head` produces a broken database.

**Fix:** Either regenerate the initial migration or add a second migration. See Phase 3 prompt §0 Fix 1 for detailed instructions.

### Bug 2: Dead `http_client` variable in TelegramAdapter.start()

`src/hestia/platforms/telegram_adapter.py` lines 47-55 create an `httpx.AsyncClient` and assign it to `http_client`, but this variable is never passed to the `Application.builder()`. The builder uses `.http_version("1.1")` which sets the version string, but the custom timeout/client configuration is lost.

**Fix:** Either pass the httpx client to the Application builder via `.get_updates_http_version("1.1").http_version("1.1")` and the appropriate `httpx_kwargs` or `.request(httpx.HTTPXRequest(...))`, OR remove the dead `http_client` variable and configure timeouts through python-telegram-bot's own builder methods. Check the python-telegram-bot v21 docs for the correct builder API.

### Bug 3: No session recovery in Telegram `on_message`

The `telegram` command in `cli.py` (line 779) uses an in-memory `user_sessions: dict[str, Session]` cache. On bot restart, this dict is empty, so every user gets a brand new session instead of resuming their existing one. The CLI commands use `session_store.get_or_create_session("cli", "default")` which correctly resumes existing sessions.

**Fix:** Replace the `user_sessions` dict lookup with:
```python
session = await session_store.get_or_create_session("telegram", platform_user)
```
This is the same pattern the CLI uses. The in-memory cache can stay as an optimization layer on top if desired (cache the result of `get_or_create_session`), but the first call for each user must check the database.

### Bug 4: No crash recovery in `telegram` command

`recover_stale_turns()` is called in `chat` (line 243) and `ask` (line 323) commands but NOT in the `telegram` command. Since the Telegram bot is the one running as a systemd service and most likely to crash mid-turn, this is exactly where crash recovery matters most.

**Fix:** Add after `orchestrator = Orchestrator(...)` in `_run()`:
```python
recovered = await orchestrator.recover_stale_turns()
if recovered:
    click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")
```

### Bug 5: No confirm_callback for Telegram orchestrator (not a bug, but needs documentation)

The Orchestrator in the `telegram` command is constructed without a `confirm_callback`. This means tools with `requires_confirmation=True` (like `write_file`) will return an error message to the model saying no confirmation handler is configured. This is acceptable behavior for now (Telegram has no confirmation UI), but it should be documented and eventually wired up (e.g., via inline keyboard buttons).

---

## Git State

- `main`: v0.1.0 tag (Phase 1a-1c)
- `origin/develop`: Phase 2a merged (`779b79a`). Local develop is ahead with Phase 2b + 2c + smoke test fix.
- `feature/phase-2b-scheduler`: merged into develop locally
- `feature/phase-2c-platform-base`: merged into develop locally
- `feature/phase-3-telegram`: current, 8 commits ahead of develop

### Pending Git Operations (Dylan does these on Mac)

1. Push develop to origin (brings Phase 2b + 2c to remote)
2. Push `feature/phase-3-telegram` to origin (or merge into develop first)

---

## Test Counts by Phase

| Phase | Tests | Delta | Key Additions |
|-------|-------|-------|---------------|
| 1a | 42 | +42 | Inference, persistence, calibration |
| 1b | 96 | +54 | Tools, context builder, artifacts, registry |
| 1c | 123 | +27 | Orchestrator, state machine, CLI, integration |
| 2a | 142 | +19 | SlotManager unit + integration, session slots |
| 2b | 196 | +54 | SchedulerStore, Scheduler engine, CLI schedule |
| 2c | 218 | +22 | Config, Platform ABC, CliPlatform, new tools |
| 3 | ~226 | +8 | TelegramAdapter, crash recovery |

---

## Architecture Decisions (ADRs)

16 ADRs in `docs/DECISIONS.md`. Key ones:
- ADR-011: Two-number calibration
- ADR-012: Turn state machine
- ADR-013: SlotManager lifecycle
- ADR-014: Scheduler design
- ADR-015: HestiaConfig typed Python dataclass
- ADR-016: Telegram adapter (HTTP/1.1, rate limiting, whitelist)

---

## Design Debt (carried forward)

1. Alembic migration incomplete (Bug 1 above — now 2 phases overdue)
2. PolicyEngine mostly stub (only retry_after_error populated)
3. No Alembic migration workflow documented
4. Artifact tools not exercised (grep_artifact, list_artifacts not built)
5. Progress visibility partially implemented (status editing added Phase 3, but no status_msg_id on Turn dataclass yet)
6. Telegram confirmation UI not implemented (Bug 5 above)

---

## Remaining Roadmap

- **Phase 4:** Long-term memory (FTS5) + Matrix dev adapter
- **Phase 5:** Subagent delegation
- **Phase 6:** Polish, docs, share

---

## How to Use This File

### If you're Claude (Cowork):
1. Read this file at the start of every session about Hestia
2. After reviewing Kimi output, update the "Current Branch & Phase", "Review Verdict", and "Git State" sections
3. When writing a Kimi prompt, fold any bugs from the current review into §0 of the next phase

### If you're Cursor:
1. Read this file at the start of every session about Hestia
2. The "Review Verdict" section tells you exactly what to look for and what bugs exist
3. After reviewing Kimi output, update this file the same way Claude would
4. Kimi prompts live in `~/hermes-audit-20260402-1703/` on Dylan's Mac (the Cowork workspace folder)
5. The design document is at `~/hermes-audit-20260402-1703/hestia-design-revised-april-2026.md`
6. When writing a Kimi prompt, follow the format established in prior prompts (same repo under the workspace folder)

### Key files for any reviewer:
- `docs/DECISIONS.md` — All ADRs
- `docs/handoffs/HESTIA_PHASE_*_REPORT_*.md` — Kimi's self-reported output per phase
- `src/hestia/persistence/schema.py` — Ground truth for database schema
- `src/hestia/orchestrator/transitions.py` — State machine transition table
- `src/hestia/config.py` — All configuration
- `pyproject.toml` — Dependencies

### Review checklist (for any tool):
1. Read the handoff report Kimi wrote (`docs/handoffs/`)
2. Read every new/modified file listed in the report
3. Check §0 cleanup items were actually done (they sometimes aren't — see Bug 1)
4. Check config fields are actually wired (not just defined)
5. Check new store methods have matching tests
6. Check CLI commands call the right store methods (not stubs)
7. Check imports are correct (Phase 2c smoke test breakage was an import issue)
8. Run mental model: "what happens on restart?" for any stateful component
9. Update this file with findings
