# Hestia — Review & Orchestration State

> **Purpose:** This file is the handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase. Whichever tool picks up the work reads this file first to understand where we are. Whoever finishes a review session updates it.
>
> **Last updated:** 2026-04-10
> **Last updated by:** Cursor

---

## Current Branch & Phase

- **Base branch:** `develop` (includes merged Phase 5)
- **Working branch:** `feature/phase-6-hardening` (to be created by Kimi)
- **Phase:** 6 — Pre-release hardening (security, failure tracking, observability, docs)
- **Status:** Prompt written, ready for Kimi build cycle.

---

## Review Verdict: Phase 5 (final)

**Overall: green.** Phase 5 merged into `develop`.

## Phase 6 Scope

Phase 6 brings Hestia to a releasable state. No new features — closing security gaps, adding failure tracking, fixing observability, and polishing docs.

### §0 — Bug fixes
- `cli.py` references `logger` but never defines it (missing import)
- `schedule_daemon` sets `confirm_callback = CliConfirmHandler()` — blocks forever on headless process; should be `None`

### §1-§2 — Security: Capability labels + tool filtering
- Add `capabilities` field to `ToolMetadata` with standardized labels (`read_local`, `write_local`, `shell_exec`, `network_egress`, `memory_read`, `memory_write`, `orchestration`)
- `PolicyEngine.filter_tools()` restricts tools by session context (subagents denied `shell_exec`/`write_local`; scheduler denied `shell_exec`)

### §3 — Security: Path sandboxing
- `read_file` and `write_file` become factories with `allowed_roots` from `StorageConfig`
- Path validation before any filesystem access

### §4 — Failure tracking
- `FailureClass` enum + `classify_error()` mapping HestiaError subclasses
- `FailureBundle` model + `FailureStore` with SQLite table + Alembic migration
- Orchestrator records failure bundles on turn failure

### §5 — Observability + CLI polish
- Centralized `setup_logging()`, `hestia status`, `hestia version`
- `FailureStore` wired into CLI bootstrap

### §6 — Documentation
- ADR-019 (capability labels), ADR-020 (failure tracking)
- README overhaul, CHANGELOG

**Prompt:** `docs/prompts/KIMI_PHASE_6_PROMPT.md`

---

## Git State

- **`develop`:** Through Phase 5 merge. All prior feature branches merged.
- **`feature/phase-6-hardening`:** To be created by Kimi from `develop`.

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
3. Telegram confirmation UI for destructive tools (inline keyboard).
4. Artifact tools (`grep_artifact`, `list_artifacts`).

---

## Remaining Roadmap

- **Phase 6:** Pre-release hardening (in progress — see `docs/prompts/KIMI_PHASE_6_PROMPT.md`).
- **Post-release:** Future systems phases (knowledge separation, skill mining, failure analysis, security auditor, adversarial evaluator, bounded auto-healing). See `hestia-future-systems-synthesis.md` and `future-systems-design.md`.

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
