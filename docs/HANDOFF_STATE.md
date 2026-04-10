# Hestia — Review & Orchestration State

> **Purpose:** This file is the handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase. Whichever tool picks up the work reads this file first to understand where we are. Whoever finishes a review session updates it.
>
> **Last updated:** 2026-04-10
> **Last updated by:** Cursor

---

## Current Branch & Phase

- **Integrated branch (pending merge):** `feature/phase-6-hardening`
- **Phase:** 6 — Pre-release hardening **complete** (merge to `develop` when ready)
- **Status:** Reviewed by Cursor; fixes applied for regressions noted below.

---

## Review Verdict: Phase 6 (final)

**Overall: green** — core security and failure-tracking goals met. Kimi delivered capability labels, `filter_tools`, path sandboxing, `FailureStore` + orchestrator wiring, schema + Alembic migration, and tests.

**Cursor follow-up fixes (same branch):**

1. **`hestia chat` regression:** Orchestrator used `confirm_callback=None` while the command set `CliConfirmHandler` on context — destructive tools could run without prompting. Fixed: `chat` now passes `CliConfirmHandler()`.
2. **`schedule_daemon`:** Still constructed `Orchestrator(..., confirm_callback=CliConfirmHandler())` despite headless intent. Fixed: `confirm_callback=None`. Status echo also used wrong variable for tick interval — fixed to `{tick}`.
3. **Scheduler tool filtering:** `platform="scheduler"` never matched real sessions (tasks use `cli` sessions). Fixed: `scheduler_tick_active` contextvar set for the duration of `Scheduler._fire_task` → `process_turn`; `DefaultPolicyEngine.filter_tools` treats it like scheduler mode.
4. **`orchestrator_factory` (delegation):** Now passes `failure_store` so subagent failures can be recorded.
5. **`cli.py`:** `logger` moved below imports (ruff E402). `FailureClass` uses `StrEnum` (ruff UP042).

**Still missing vs Phase 6 prompt (non-blocking for merge):**

- `setup_logging()`, `hestia status`, `hestia version`, `hestia failures` CLI commands
- README overhaul and CHANGELOG expansion (prompt §6)
- Phase 6 handoff report under `docs/handoffs/` (Kimi did not add one)

**Kimi prompt for the above:** `docs/prompts/KIMI_PHASE_6_FOLLOWUP_PROMPT.md` (stay on `feature/phase-6-hardening`; no merge to `develop` unless Dylan says so).

**Design docs added (committed with branch):**

- `docs/roadmap/future-systems-deferred-roadmap.md`
- `docs/design/matrix-integration.md`

---

## Git State

- **`feature/phase-6-hardening`:** Phase 6 implementation + review fixes; ready to merge into `develop`.
- **`develop`:** Through Phase 5 until merge.

---

## Test Counts

| Phase | Tests (approx.) |
|-------|-----------------|
| 6 final | ~295 |

Run: `uv run pytest tests/unit/ tests/integration/ -q`

---

## Architecture Decisions (ADRs)

20 ADRs including **ADR-019** (capability labels + tool filtering), **ADR-020** (failure bundles).

---

## Design Debt (carried forward)

1. Policy delegation **replaces** the model’s tool batch with one `delegate_task` result (duplicated text for multiple `tool_call_id`s except the first). Refine UX later if needed.
2. Matrix adapter + integration harness (design stretch).
3. Telegram confirmation UI for destructive tools (inline keyboard).
4. Artifact tools (`grep_artifact`, `list_artifacts`).

---

## Remaining Roadmap

- **Phase 6 follow-ups:** `hestia status` / `version` / `failures`, `setup_logging`, README + CHANGELOG (see prompt §5–§6).
- **Post-release:** Deferred roadmap in `docs/roadmap/future-systems-deferred-roadmap.md`; Matrix plan in `docs/design/matrix-integration.md`.

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
