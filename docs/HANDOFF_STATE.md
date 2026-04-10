# Hestia — Review & Orchestration State

> **Purpose:** This file is the handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase. Whichever tool picks up the work reads this file first to understand where we are. Whoever finishes a review session updates it.
>
> **Last updated:** 2026-04-10
> **Last updated by:** Cursor

---

## Current Branch & Phase

- **Reviewed branch:** `feature/phase-5-subagent-delegation` (not merged to `develop` at last review)
- **Phase:** 5 — Subagent delegation (partial delivery)
- **Next:** Phase 5b completion merge, or fold §0 of Phase 6 prompt with items below
- **Status:** Review complete. **Do not ship** as “Phase 5 done” until blockers are fixed (see Verdict).

---

## Review Verdict: Phase 5

**Overall: yellow — merge only after fixes or explicit acceptance of partial scope.**

Kimi delivered solid **§0 (Phase 4 follow-ups)** and useful **infrastructure** (policy hook, transitions, `delegate_task` skeleton, ADR-018, direct-tool confirmation in `_dispatch_tool_call`). The Phase 5 handoff report correctly lists **remaining work**.

### Critical (fixed in repo after review)

1. **`delegate_task.py` referenced `TurnState` without importing it** — would raise `NameError` when building `SubagentResult`. Importing `TurnState` from `orchestrator.types` **causes a circular import** (`builtin` → `orchestrator` → `engine` → `builtin`). **Fix applied:** use existing `state_value == "failed"` for the `error` field (same pattern as the rest of the function).

### Blockers before calling Phase 5 “complete”

2. **`delegate_task` is not registered in `cli.py`** — the model never sees the tool; delegation is unreachable in normal use.

3. **Orchestrator does not use `AWAITING_SUBAGENT` or `policy.should_delegate()`** — transitions were added to `ALLOWED_TRANSITIONS`, but `engine.py` still goes `EXECUTING_TOOLS` → `BUILDING_CONTEXT` with no delegation branch. The new edges are unused.

4. **No unit/integration tests for `delegate_task`** — zero test coverage for the new tool; the `TurnState` bug was latent for that reason.

### §0 verification (Phase 4 prompt — done)

| Item | Verdict |
|------|---------|
| Session context for `save_memory` | OK — `contextvars.current_session_id` set in `process_turn` / reset in `finally` |
| Stricter tag filter | OK — quoted phrase in `MemoryStore.list_memories` + tests |
| Naive datetime documented | OK — class docstring on `MemoryStore` |
| `_bootstrap_db` helper | OK — used across CLI commands |
| Terminal kill `PermissionError` | OK — handled in `terminal.py` |

### Tests (reviewer run)

- `uv run pytest tests/unit/ -q` — **245 passed** (full permissions; terminal timeout test needs kill permission).

---

## Resolved earlier (do not re-file)

- Phase 3 Telegram / Alembic fixes on `develop` via Phase 4 merge.
- Phase 4 memory stack (FTS5, tools, CLI).

---

## Git State

- **`develop`:** Through Phase 4 merge (`2a2a011` and ancestors).
- **`feature/phase-5-subagent-delegation`:** Phase 5 work + post-review fix for `TurnState` import (commit after review if you commit the fix).
- **Recommended:** After addressing blockers 2–4 (or scoping them to Phase 5b), merge feature branch into `develop` and push.

---

## Test Counts by Phase

| Phase | Tests (approx.) | Notes |
|-------|-----------------|-------|
| 5 | ~245 | +4 vs Phase 4 per Kimi; no delegate_task tests |

---

## Architecture Decisions (ADRs)

18 ADRs in `docs/DECISIONS.md` including **ADR-018** (subagent delegation).

---

## Design Debt (carried forward)

1. Finish Phase 5: register `delegate_task`, wire `should_delegate` + `AWAITING_SUBAGENT` (or document intentional deferral and narrow ADR-018 scope).
2. PolicyEngine still mostly stub beyond `retry_after_error` and `should_delegate` heuristic.
3. Matrix adapter + integration harness (original Phase 4 design stretch).
4. Telegram confirmation UI.
5. Artifact tools (`grep_artifact`, `list_artifacts`).

---

## Remaining Roadmap

- **Phase 5b (recommended):** CLI registration, orchestrator delegation loop, tests — see `docs/prompts/KIMI_PHASE_5_PROMPT.md` “Next Steps” and fold into §0 of next Kimi prompt.
- **Phase 6:** Polish, docs, share (`docs/hestia-design-revised-april-2026.md`).

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
4. Kimi prompts: `docs/prompts/`
5. Design reference: `docs/hestia-design-revised-april-2026.md`

### Key files for any reviewer:

- `docs/DECISIONS.md` — All ADRs
- `docs/handoffs/HESTIA_PHASE_*_REPORT_*.md` — Kimi's self-reported output per phase
- `src/hestia/persistence/schema.py` — Relational schema
- `src/hestia/orchestrator/transitions.py` — State machine transition table
- `src/hestia/config.py` — Configuration
- `pyproject.toml` — Dependencies

### Review checklist (for any tool):

1. Read the handoff report Kimi wrote (`docs/handoffs/`)
2. Read every new/modified file listed in the report
3. Check §0 cleanup items were actually done
4. Check new tools are registered in `cli.py` if they should be visible to the model
5. Check state machine changes are exercised in `engine.py`, not only in `transitions.py`
6. Run `pytest tests/unit/`
7. Update this file with findings
