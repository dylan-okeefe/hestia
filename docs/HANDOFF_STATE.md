# Hestia — Review & Orchestration State

> **Purpose:** This file is the handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase. Whichever tool picks up the work reads this file first to understand where we are. Whoever finishes a review session updates it.
>
> **Last updated:** 2026-04-10
> **Last updated by:** Cursor

---

## Current Branch & Phase

- **Integrated branch:** `develop` (includes merged `feature/phase-4-memory`)
- **Phase:** 4 — Long-term memory (FTS5) **shipped and merged**
- **Next phase:** 5 — Subagent delegation (see `docs/prompts/KIMI_PHASE_5_PROMPT.md`)
- **Status:** Phase 4 review complete. Green for Phase 5 Kimi cycle.

---

## Review Verdict: Phase 4 (post-merge of Phase 3 fixes)

**Overall: green.** Phase 3 review items were fixed in commit `f22d508` (Alembic, Telegram session recovery, crash recovery, dead `http_client`). Phase 4 added MemoryStore, memory tools, CLI `memory` group, ADR-017.

### Findings for Phase 5 §0 (cleanup + follow-ups)

1. **Memory tools omit `session_id` on save** — `MemoryStore.save()` supports `session_id`, but `save_memory` (tool) and CLI `memory add` never pass it. Agent-created memories cannot be attributed to a session. **Fix:** Thread current session id into tool execution (e.g. `contextvars`, or extend `ToolRegistry.call` / orchestrator dispatch with an execution context dict) and pass `session_id` into `make_save_memory_tool` (or equivalent).

2. **`list_memories` tag filter uses FTS `tags MATCH`** — Works but can match unintended rows (stemming / token overlap). **Fix (optional):** Tighten tag filtering (exact tag match or `tags : "phrase"` style) if precise tags matter; add tests.

3. **Naive datetimes in `MemoryStore.save()`** — Uses `datetime.now()` without timezone, consistent with rest of persistence. **Fix (optional):** Document or align with project-wide datetime strategy (UTC-aware vs naive).

4. **CLI bootstrap repetition** — Many commands each call `await db.connect()`, `create_tables()`, and `await memory_store.create_table()`. Harmless (`IF NOT EXISTS`) but noisy. **Style:** Consider a shared async startup helper used by commands that need DB + FTS, or document the pattern as intentional.

5. **Terminal unit test in restricted environments** — `TestTerminal.test_timeout` can fail with `PermissionError` on `proc.kill()` under sandboxed CI. Not a product bug; **optional:** skip or mock when kill is denied.

6. **Telegram `confirm_callback`** — Still absent; documented in `cli.py`. Future: inline keyboards. No Phase 5 §0 code change required unless wiring confirmation is in scope.

---

## Resolved (was Phase 3 §0 / HANDOFF_STATE bugs — do not re-file)

- Initial Alembic migration includes `scheduled_tasks` — revision `7368d8100cae` (`migrations/versions/7368d8100cae_initial_schema.py`).
- Telegram: `get_or_create_session`, `recover_stale_turns`, no dead httpx client, ADR-016 behavior.

---

## Git State

- **`develop`:** Should contain merged `feature/phase-4-memory` (Phase 3 + Phase 4 + Phase 3 cleanup commit `f22d508`).
- **`feature/phase-4-memory`:** Feature branch; merge target was `develop`.
- **`main`:** Behind develop; merge to `main` when you cut a release.

### Remote (Dylan / CI)

Push `develop` after merge when ready: `git push origin develop`.

---

## Test Counts by Phase

| Phase | Tests (approx.) | Key Additions |
|-------|-----------------|---------------|
| 1a | 42 | Inference, persistence, calibration |
| 1b | 96 | Tools, context, artifacts |
| 1c | 123 | Orchestrator, CLI |
| 2a | 142 | SlotManager |
| 2b | 196 | Scheduler |
| 2c | 218 | Platform base, HestiaConfig |
| 3 | ~226 | Telegram adapter, status editing, deploy |
| 4 | ~241 | MemoryStore FTS5, memory tools, `memory` CLI |

---

## Architecture Decisions (ADRs)

17 ADRs in `docs/DECISIONS.md`. Notable:

- ADR-011 — Two-number calibration
- ADR-012 — Turn state machine
- ADR-013 — SlotManager
- ADR-014 — Scheduler
- ADR-015 — HestiaConfig
- ADR-016 — Telegram adapter
- ADR-017 — FTS5 long-term memory

---

## Design Debt (carried forward)

1. PolicyEngine mostly stub (beyond retry_after_error)
2. Alembic migration workflow still worth a short doc in `docs/` when someone has time
3. Artifact tools: `grep_artifact`, `list_artifacts` not built; TTL/cleanup for ArtifactStore
4. Telegram confirmation UI not implemented (inline keyboard)
5. Matrix adapter + Matrix integration tests (Phase 4 design doc scope; not shipped in Phase 4 branch)

---

## Remaining Roadmap

- **Phase 5:** Subagent delegation (`docs/prompts/KIMI_PHASE_5_PROMPT.md`)
- **Phase 6:** Polish, docs, share (`docs/hestia-design-revised-april-2026.md` §7)

---

## How to Use This File

### If you're Claude (Cowork):

1. Read this file at the start of every session about Hestia
2. After reviewing Kimi output, update the "Current Branch & Phase", "Review Verdict", and "Git State" sections
3. When writing a Kimi prompt, fold any bugs from the current review into §0 of the next phase

### If you're Cursor:

1. Read this file at the start of every session about Hestia
2. The "Review Verdict" section lists active findings and resolved history
3. After reviewing Kimi output, update this file the same way Claude would
4. Kimi prompts: this repo keeps canonical copies under `docs/prompts/`; Dylan may also copy to the Cowork workspace folder
5. Design reference: `docs/hestia-design-revised-april-2026.md`
6. When writing a Kimi prompt, follow the format established in prior phases (§-1 merge, §0 cleanup, §1+ features, handoff report, Critical Rules Recap)

### Key files for any reviewer:

- `docs/DECISIONS.md` — All ADRs
- `docs/handoffs/HESTIA_PHASE_*_REPORT_*.md` — Kimi's self-reported output per phase
- `src/hestia/persistence/schema.py` — Ground truth for relational schema (FTS `memory` table is DDL in MemoryStore)
- `src/hestia/orchestrator/transitions.py` — State machine transition table
- `src/hestia/config.py` — Configuration
- `pyproject.toml` — Dependencies

### Review checklist (for any tool):

1. Read the handoff report Kimi wrote (`docs/handoffs/`)
2. Read every new/modified file listed in the report
3. Check §0 cleanup items were actually done
4. Check config fields are actually wired (not just defined)
5. Check new store methods have matching tests
6. Check CLI commands call the right store methods (not stubs)
7. Check imports are correct
8. Run mental model: "what happens on restart?" for any stateful component
9. Update this file with findings
