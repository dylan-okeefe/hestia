# Hestia — Review & Orchestration State

> **Purpose:** This file is the handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase. Whichever tool picks up the work reads this file first to understand where we are. Whoever finishes a review session updates it.
>
> **Last updated:** 2026-04-10
> **Last updated by:** Cursor

---

## Current Branch & Phase

- **Integrated branch:** `develop` (includes merged Phase 5)
- **Phase:** 5 — Subagent delegation **complete** (CLI registration, policy path, `AWAITING_SUBAGENT`, tests, `delegate_task` async callback fix)
- **Next phase:** 6 — Polish, docs, share (see design doc)
- **Status:** Green to merge Phase 5 branch into `develop`.

---

## Review Verdict: Phase 5 (final)

**Overall: green.**

Delivered:

- **`delegate_task`** registered in `cli.py` via `orchestrator_factory()` (shared registry; `ctx.obj["confirm_callback"]` set per command — CLI `CliConfirmHandler`, Telegram `None`).
- **Policy-driven delegation:** When `should_delegate(...)` is true and `delegate_task` is registered, orchestrator transitions `EXECUTING_TOOLS` → `AWAITING_SUBAGENT` → runs one `delegate_task` via `_execute_policy_delegation` → `EXECUTING_TOOLS` → `BUILDING_CONTEXT`, with one tool result per model `tool_call_id`.
- **`DefaultPolicyEngine`:** `session.platform == "subagent"` skips delegation (no recursion).
- **`delegate_task`:** Subagent `respond_callback` is **async** (sync lambdas caused `TypeError` after `DONE`, then bogus `DONE`→`FAILED` transition).
- **Tests:** `tests/unit/test_subagent_delegation.py` (mocked delegate + full policy path); policy and fake-policy signatures updated.

---

## Git State

- **`feature/phase-5-subagent-delegation`:** Phase 5 completion commits (merge into `develop`).
- **`develop`:** Through Phase 4 merge until Phase 5 merge.

---

## Test Counts

| Phase | Tests (approx.) |
|-------|-----------------|
| 5 final | ~254 |

Run: `uv run pytest tests/unit/ tests/integration/ -q`

---

## Architecture Decisions (ADRs)

18 ADRs including **ADR-018** (subagent delegation).

---

## Design Debt (carried forward)

1. Policy delegation **replaces** the model’s tool batch with one `delegate_task` result (duplicated text for multiple `tool_call_id`s except the first). Refine UX later if needed.
2. Matrix adapter + integration harness (design stretch).
3. Telegram confirmation UI for destructive tools.
4. Artifact tools (`grep_artifact`, `list_artifacts`).

---

## Remaining Roadmap

- **Phase 6:** Polish, docs, share (`docs/hestia-design-revised-april-2026.md`).

---

## How to Use This File

### If you're Claude (Cowork):

1. Read this file at the start of every session about Hestia
2. After reviewing Kimi output, update the "Current Branch & Phase", "Review Verdict", and "Git State" sections
3. When writing a Kimi prompt, fold any bugs from the current review into §0 of the next phase

### If you're Cursor:

1. Read this file at the start of every session about Hestia
2. Kimi prompts: `docs/prompts/`
3. Design reference: `docs/hestia-design-revised-april-2026.md`

### Key files for any reviewer:

- `docs/DECISIONS.md` — All ADRs
- `docs/handoffs/HESTIA_PHASE_*_REPORT_*.md` — Kimi's self-reported output per phase
- `src/hestia/orchestrator/engine.py` — Turn loop and delegation
- `src/hestia/orchestrator/transitions.py` — State machine
- `src/hestia/cli.py` — Tool registration and confirm callback wiring

### Review checklist (for any tool):

1. Read the handoff report Kimi wrote (`docs/handoffs/`)
2. New tools registered in `cli.py` when they should be visible to the model
3. `respond_callback` is async wherever the orchestrator awaits it
4. Run `pytest tests/unit/ tests/integration/`
5. Update this file with findings
