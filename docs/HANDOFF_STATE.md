# Hestia — Review & Orchestration State

> **Purpose:** Handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase.
>
> **Last updated:** 2026-04-11
> **Last updated by:** Cursor (post–Phase 6 closeout review; HANDOFF narrative aligned)

---

## Kimi in Cursor terminal — paste this now

Kimi is running in `~/Hestia`. Send **one** message:

```text
Read docs/prompts/KIMI_CURRENT.md, then execute the full "Current task" section by following the linked prompt file to the end. Report git log -8, pytest, and branch state.
```

**Single source of truth for “what Kimi does next”:** [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md). After each Kimi cycle, **Cursor** updates that file and this section.

### Orchestration loop (Cursor)

1. Kimi finishes → **review** (diff, handoff, pytest).
2. If issues → write **`KIMI_PHASE_*_FOLLOWUP*.md`** or amend `KIMI_CURRENT.md` with a tight fix list; point Kimi there.
3. If green → **set `KIMI_CURRENT.md` “Current task”** to the next phase prompt (after Phase 6 closeout → Phase 7 Matrix is already drafted).
4. **Paste** the block above again (or a variant that names the new prompt file).

---

## Current branch and phase

- **Branch:** `develop` (local may be **ahead of** `origin/develop` until you `git push`)
- **Phase:** **6 complete** on `develop` (observability stack, deploy README, handoff SHAs). **Active work:** **Phase 7 Matrix** — follow [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md).
- **Closeout verification (2026-04-11):** README lists `hestia-llama.service` / `hestia-agent.service` and valid `deploy/README.md`; pytest **311 passed** on clean tree.

---

## Kimi prompt order (orchestration — Cursor does not implement)

1. ~~**Closeout + gitflow**~~ — Done (see `git log` on `develop`, e.g. `4cf2fc7`, `de7159f`, `81462d1`).
2. **Matrix (Phase 7):** [`docs/prompts/KIMI_PHASE_7_MATRIX.md`](prompts/KIMI_PHASE_7_MATRIX.md) — branch `feature/phase-7-matrix` from `develop`; adapter, config, CLI, tests per [`docs/design/matrix-integration.md`](design/matrix-integration.md).

**Earlier prompts (reference only):**

- [`KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md) — closeout spec (completed)
- [`KIMI_PHASE_6_FOLLOWUP_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_PROMPT.md) — original follow-up scope
- [`KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md) — review-fixes pass

---

## Git state

| Branch | Role |
|--------|------|
| `develop` | **Phase 6 tip** — merge / fast-forward complete locally |
| `feature/phase-6-hardening` | Optional remote history; **new work** cuts `feature/phase-7-matrix` from `develop` |

---

## Review verdict: Phase 6 (post-closeout)

**Green.** Capability filtering, path sandboxing, failure store, CLI observability, deploy docs, and tests are on `develop` with a clean working tree.

**Housekeeping (not blocking Phase 7):** `PytestUnhandledThreadExceptionWarning` (aiosqlite / closed loop); ruff/mypy debt unchanged from prior notes.

---

## Test Counts

| Snapshot | Count |
|----------|-------|
| Last `pytest tests/unit/ tests/integration/ -q` on `develop` (2026-04-11) | **311 passed** |

Run: `uv run pytest tests/unit/ tests/integration/ -q`

---

## Architecture Decisions (ADRs)

20 ADRs (ADR-019, ADR-020 for Phase 6). **Phase 7 Matrix** should add **ADR-021** (per Matrix prompt).

---

## Quality Checks (orienting)

| Tool | Notes |
|------|--------|
| pytest | **311 passed** on reviewed tree; fix HANDOFF if your run differs |
| ruff | Large pre-existing debt possible; run on touched files before pushing Phase 7 |
| mypy | Pre-existing errors in some modules; new Matrix code should type-check |

---

## Design Debt (carried forward)

1. Policy delegation batch UX (duplicate `tool_call_id` text).
2. **Matrix** — design in `docs/design/matrix-integration.md`; implementation = Phase 7 prompt.
3. Telegram inline confirmation for destructive tools.
4. Artifact tools (`grep_artifact`, `list_artifacts`).
5. aiosqlite pytest thread warnings (housekeeping).

---

## Remaining roadmap

1. Kimi: **Phase 7 Matrix** + tests ([`KIMI_PHASE_7_MATRIX.md`](prompts/KIMI_PHASE_7_MATRIX.md)).
2. Long-term: `docs/roadmap/future-systems-deferred-roadmap.md`.

---

## How to Use This File

### Claude / Cursor

1. Read at start of each Hestia session.
2. After Kimi delivers work: update verdict, test counts, git state, prompt pointers.
3. Next Kimi cycle: **Matrix** (`KIMI_CURRENT.md` → `KIMI_PHASE_7_MATRIX.md`).

### Review checklist

1. Read Kimi handoff under `docs/handoffs/`
2. `pytest tests/unit/ tests/integration/`
3. New platform commands register tools and use async `respond_callback`
4. Update this file
