# Hestia — Review & Orchestration State

> **Purpose:** Handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase.
>
> **Last updated:** 2026-04-11
> **Last updated by:** Cursor (orchestration + extended review; no code fixes)

---

## Current Branch & Phase

- **Branch:** `feature/phase-6-hardening`
- **Phase:** 6 — pre-release hardening + follow-up **code complete in working tree**, **not yet committed**
- **Blocker before merge:** Kimi must **commit** all changes, finish **doc closeout** (see below), then Dylan (or Kimi per prompt) runs **gitflow** merge to `develop`.

---

## Cursor review: full working-tree diff (Phase 6 follow-up)

**Scope:** ~31 files, **+806 / −339** lines vs last commit (`git diff HEAD --stat`).

**Verdict on “the rest” of the changes (beyond CLI/status/failures):**

| Area | Assessment |
|------|------------|
| `config.py`, `context/builder.py`, `slot_manager.py`, `registry.py`, `telegram_adapter.py`, `policy/default.py`, `scheduler/engine.py`, `orchestrator/engine.py` | Almost entirely **line-wrapping / ruff-style formatting**. **No semantic risk** spotted in sampled diffs. |
| `persistence/sessions.py`, `scheduler.py`, `failure_store.py` | **Functional** changes align with prior review (turn stats, `summary_stats`, class filter, etc.). |
| `tests/unit/test_cli_scheduler.py` (large) | **CliRunner invoke formatting** + structure; behavior should be unchanged — **rely on pytest**. |
| Other test tweaks | Small import/assert adjustments; **311 tests passed** in last Cursor run (`uv run pytest tests/unit/ tests/integration/ -q`). |

**Remaining doc issues (Kimi — do not merge until fixed):**

1. **README Deploy** — Still lists non-existent `hestia-scheduler.service`, `hestia-telegram.service`, and broken `deploy/README.md` link. **Fix per** [`docs/prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md) §1.1.
2. **Phase 6 handoff report** — Remove phantom `tools/decorators.py`; fill **real commit SHAs** after commit. Same closeout prompt §1.2.

**Pytest note:** 2× `PytestUnhandledThreadExceptionWarning` (aiosqlite / closed loop) — **housekeeping** for a future Kimi cycle; not a merge blocker.

---

## Review Verdict: Phase 6 (code)

**Green** for security, failure tracking, observability CLI, and store queries — pending **commit + doc closeout** above.

---

## Kimi prompt order (orchestration — Cursor does not implement)

1. **Closeout + gitflow:** [`docs/prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md) — README deploy, handoff SHAs, commits, merge `feature/phase-6-hardening` → `develop`.
2. **Matrix (Phase 7):** [`docs/prompts/KIMI_PHASE_7_MATRIX.md`](prompts/KIMI_PHASE_7_MATRIX.md) — new branch `feature/phase-7-matrix` from updated `develop`; adapter, config, CLI, tests per [`docs/design/matrix-integration.md`](design/matrix-integration.md).

**Earlier prompts (reference only):**

- [`KIMI_PHASE_6_FOLLOWUP_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_PROMPT.md) — original follow-up scope
- [`KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md) — most items addressed in tree; deploy/handoff still open

---

## Git State

| Branch | Role |
|--------|------|
| `feature/phase-6-hardening` | **Uncommitted WIP** — Kimi commits here, then merge per closeout prompt |
| `develop` | Still at Phase 5 merge until Phase 6 lands |

**Cursor did not merge** — merge is explicit in closeout prompt for Dylan/Kimi.

---

## Test Counts

| Snapshot | Count |
|----------|-------|
| Last `pytest tests/unit/ tests/integration/ -q` on this tree | **311 passed** |

Run: `uv run pytest tests/unit/ tests/integration/ -q`

---

## Architecture Decisions (ADRs)

20 ADRs (ADR-019, ADR-020 for Phase 6). **Phase 7 Matrix** should add **ADR-021** (per Matrix prompt).

---

## Quality Checks (orienting)

| Tool | Notes |
|------|--------|
| pytest | **311 passed** on reviewed tree; fix HANDOFF if your run differs |
| ruff | Run before merge; large pre-existing debt possible outside touched files |
| mypy | Pre-existing errors in some modules; new Matrix code should type-check |

---

## Design Debt (carried forward)

1. Policy delegation batch UX (duplicate `tool_call_id` text).
2. **Matrix** — design in `docs/design/matrix-integration.md`; implementation = Phase 7 prompt.
3. Telegram inline confirmation for destructive tools.
4. Artifact tools (`grep_artifact`, `list_artifacts`).
5. aiosqlite pytest thread warnings (housekeeping).

---

## Remaining Roadmap

1. Kimi: **Phase 6 closeout** + merge to `develop` (prompt above).
2. Kimi: **Phase 7 Matrix** + tests (prompt above).
3. Long-term: `docs/roadmap/future-systems-deferred-roadmap.md`.

---

## How to Use This File

### Claude / Cursor

1. Read at start of each Hestia session.
2. After Kimi delivers work: update verdict, test counts, git state, prompt pointers.
3. Next Kimi cycle: use **closeout** then **Matrix** prompts in order.

### Review checklist

1. Read Kimi handoff under `docs/handoffs/`
2. `pytest tests/unit/ tests/integration/`
3. New platform commands register tools and use async `respond_callback`
4. Update this file
