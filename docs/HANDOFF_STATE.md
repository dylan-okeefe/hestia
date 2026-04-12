# Hestia — Review & Orchestration State

> **Purpose:** Handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase.
>
> **Last updated:** 2026-04-12
> **Last updated by:** Cursor (Kimi CLI + `.kimi-done` orchestration; Phase 7 = cleanup design doc)

---

## Kimi — dispatch (pick one)

### A — One-shot CLI (preferred when `kimi` supports `--prompt`)

From the repo root:

```bash
chmod +x scripts/kimi-run-current.sh   # once
./scripts/kimi-run-current.sh > .kimi-output.log 2>&1
```

The script defaults to **`--quiet`** (final assistant message only; see Kimi docs). For full output: `KIMI_VERBOSE=1 ./scripts/kimi-run-current.sh` or pass **`--print`** explicitly. Other Kimi flags go after the script name.

**Completion signal:** wait until **`./scripts/kimi-run-current.sh` exits**, then confirm **`.kimi-done`** exists and read it before review.

### B — Interactive Kimi (fallback)

Kimi is running in `~/Hestia`. Send **one** message:

```text
Read docs/prompts/KIMI_CURRENT.md, then execute the full "Current task" section including every linked file under docs/design/. Finish with the handoff steps and .kimi-done artifact described in the active design spec.
```

**Single source of truth for “what Kimi does next”:** [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md). After each Kimi cycle, **Cursor** updates that file and this section.

### Orchestration loop (Cursor)

1. **Wait for done:** Kimi CLI exits **and** `.kimi-done` exists with `HESTIA_KIMI_DONE=1` (or read `.kimi-output.log` if Kimi was redirected).
2. **Review:** diff (`develop..HEAD` or merge base), handoff notes, `uv run pytest tests/unit/ tests/integration/ -q`.
3. If issues → add a follow-up design section or a tight `KIMI_PHASE_*_FOLLOWUP*.md`; point `KIMI_CURRENT.md` at it.
4. If green → merge per gitflow, update this file, set `KIMI_CURRENT.md` for the next task (Matrix remains in [`docs/design/matrix-integration.md`](design/matrix-integration.md)).
5. Remove stale **`.kimi-done`** before the next Kimi launch (the helper script does this automatically).
6. **Loop log:** After each review (and whenever you set the next prompt), append a **dated** section to [`docs/orchestration/kimi-loop-log.md`](orchestration/kimi-loop-log.md) with the full narrative (commands, branches, SHAs, pytest/ruff notes, files touched, follow-up text). In the **Cursor chat**, reply with only a **brief** bullet summary of the same loop instance.

---

## Current branch and phase

- **Branch:** `develop` (local may be **ahead of** `origin/develop` until you `git push`)
- **Phase:** **6 complete** on `develop`. **Active Kimi work:** **Phase 7 cleanup** — spec is **[`docs/design/kimi-hestia-phase-7-cleanup.md`](design/kimi-hestia-phase-7-cleanup.md)** (branch `feature/phase-7-cleanup`). Orchestration pointer: [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md).
- **Closeout verification (2026-04-11):** README lists `hestia-llama.service` / `hestia-agent.service` and valid `deploy/README.md`; pytest **311 passed** on clean tree.

---

## Kimi prompt order (orchestration — Cursor does not implement)

1. ~~**Closeout + gitflow**~~ — Done (see `git log` on `develop`, e.g. `4cf2fc7`, `de7159f`, `81462d1`).
2. **Phase 7 cleanup (current):** [`docs/design/kimi-hestia-phase-7-cleanup.md`](design/kimi-hestia-phase-7-cleanup.md) — branch **`feature/phase-7-cleanup`** from `develop`.
3. **Matrix (next, after cleanup):** [`docs/design/matrix-integration.md`](design/matrix-integration.md) — cut a feature branch from updated `develop` when Cursor points `KIMI_CURRENT.md` there.
4. **Phase 8+ plan:** [`docs/design/hestia-phase-8-plus-roadmap.md`](design/hestia-phase-8-plus-roadmap.md) (reference for later prompts).

**Earlier prompts (reference only):**

- [`KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md) — closeout spec (completed)
- [`KIMI_PHASE_6_FOLLOWUP_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_PROMPT.md) — original follow-up scope
- [`KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md) — review-fixes pass

---

## Git state

| Branch | Role |
|--------|------|
| `develop` | Phase 6 tip — merge / fast-forward complete locally |
| `feature/phase-7-cleanup` | **Active Kimi target** for Phase 7 cleanup spec |
| `feature/phase-6-hardening` | Optional remote history |

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

20 ADRs (ADR-019, ADR-020 for Phase 6). **Matrix** work should add **ADR-021** when that phase starts (per `matrix-integration.md`).

---

## Quality Checks (orienting)

| Tool | Notes |
|------|-------|
| pytest | **311 passed** on reviewed tree; fix HANDOFF if your run differs |
| ruff | Large pre-existing debt possible; run on touched files before pushing |
| mypy | Pre-existing errors in some modules; new code should type-check |

---

## Design Debt (carried forward)

1. Policy delegation batch UX (duplicate `tool_call_id` text).
2. **Matrix** — [`docs/design/matrix-integration.md`](design/matrix-integration.md); schedule after Phase 7 cleanup.
3. Telegram inline confirmation for destructive tools.
4. Artifact tools (`grep_artifact`, `list_artifacts`).
5. aiosqlite pytest thread warnings (housekeeping).

---

## Remaining roadmap

1. Kimi: **Phase 7 cleanup** ([`kimi-hestia-phase-7-cleanup.md`](design/kimi-hestia-phase-7-cleanup.md)).
2. Kimi: **Matrix** adapter + tests ([`matrix-integration.md`](design/matrix-integration.md)).
3. Long-term: `docs/roadmap/future-systems-deferred-roadmap.md` and Phase 8+ design doc.

---

## How to Use This File

### Claude / Cursor

1. Read at start of each Hestia session.
2. After Kimi delivers work: update verdict, test counts, git state, prompt pointers; remove or acknowledge `.kimi-done`.
3. Next Kimi cycle: follow `KIMI_CURRENT.md` (currently → Phase 7 cleanup design).

### Review checklist

1. Read `.kimi-done` and Kimi logs if present; read Kimi handoff under `docs/handoffs/` when applicable
2. `pytest tests/unit/ tests/integration/`
3. New platform commands register tools and use async `respond_callback`
4. Update this file
