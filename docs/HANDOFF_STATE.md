# Hestia — Review & Orchestration State

> **Purpose:** Handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase.
>
> **Last updated:** 2026-04-12
> **Last updated by:** Cursor (Phase 7 merged to `develop`; orchestration restored; L01 Matrix next)

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
Read docs/prompts/KIMI_CURRENT.md, then execute the full "Current task" section including every linked file under docs/design/. Finish with the handoff steps and .kimi-done artifact described in the active loop spec.
```

**Single source of truth for "what Kimi does next":** [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md). After each Kimi cycle, **Cursor** updates that file and this section.

### Orchestration loop (Cursor)

1. **Wait for done:** Kimi CLI exits **and** `.kimi-done` exists with `HESTIA_KIMI_DONE=1` (or read `.kimi-output.log` if Kimi was redirected).
2. **Review:** diff (`develop..HEAD` or merge base), handoff notes, `uv run pytest tests/unit/ tests/integration/ -q`.
3. If issues → add a follow-up design section or a tight `KIMI_PHASE_*_FOLLOWUP*.md`; point `KIMI_CURRENT.md` at it.
4. If green → merge per gitflow, update this file, set `KIMI_CURRENT.md` for the next queue row in [`docs/orchestration/kimi-phase-queue.md`](orchestration/kimi-phase-queue.md).
5. Remove stale **`.kimi-done`** before the next Kimi launch (the helper script does this automatically).
6. **Loop log:** After each review (and whenever you set the next prompt), append a **dated** section to [`docs/orchestration/kimi-loop-log.md`](orchestration/kimi-loop-log.md) with the full narrative. In the **Cursor chat**, reply with only a **brief** bullet summary of the same loop instance.

---

## Current branch and phase

- **Branch:** `develop` (local **ahead of** `origin/develop` until you `git push` — includes Phase 7 cleanup + orchestration docs)
- **Phase 7:** **Merged** — commit **`265003b`** on `develop` ("fix: phase 7 cleanup — bugs, security, dead code").
- **Active Kimi work:** **L01 Matrix adapter** — [`docs/orchestration/kimi-loops/L01-matrix-adapter.md`](orchestration/kimi-loops/L01-matrix-adapter.md) + product design [`docs/design/matrix-integration.md`](design/matrix-integration.md). Pointer: [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md).

**Phase 7 summary (merged):**

1. `tool_chain` UnboundLocalError fix in orchestrator error handler  
2. `sqlalchemy as sa` import ordering in `db.py`  
3. Path sandboxing for `list_dir` (factory)  
4. Deduplicated `CliConfirmHandler` in CLI  
5. Removed unsandboxed `read_file` / `write_file` fallbacks  
6. SSRF protection on `http_get`  
7. Removed dead `COMPRESSING` state  

---

## Kimi prompt order (see [`docs/orchestration/kimi-phase-queue.md`](orchestration/kimi-phase-queue.md))

1. ~~Closeout + gitflow~~ — Done  
2. ~~Phase 7 cleanup~~ — Done (`265003b` on `develop`)  
3. **L01 Matrix adapter** — `L01-matrix-adapter.md` + `matrix-integration.md`  
4. **L02–L08** — Phase 8a through Phase 13 per queue table  

**Earlier prompts (reference only):**

- [`KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md) — closeout spec (completed)  
- [`KIMI_PHASE_6_FOLLOWUP_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_PROMPT.md)  
- [`KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md)  
- [`kimi-hestia-phase-7-cleanup.md`](design/kimi-hestia-phase-7-cleanup.md) — Phase 7 spec (completed)  

---

## Git state

| Branch | Role |
|--------|------|
| `develop` | **Tip** — Phase 7 cleanup + orchestration commits (not yet pushed) |
| `feature/phase-7-cleanup` | Historical; merged into `develop` locally |
| `feature/phase-6-hardening` | Optional remote history |

---

## Review verdict: Phase 7

**Green.** All seven cleanup items landed in **`265003b`** (see summary above).

**Tests:** **309 passed** (baseline 311; two COMPRESSING-related tests removed, new tests for §1, §3, §6).

**Ruff:** Touched files clean; pre-existing debt elsewhere.

---

## Test Counts

| Snapshot | Count |
|----------|-------|
| Last `pytest tests/unit/ tests/integration/ -q` on `develop` after Phase 7 merge (2026-04-12) | **309 passed** |

Run: `uv run pytest tests/unit/ tests/integration/ -q`

---

## Architecture Decisions (ADRs)

20 ADRs (ADR-019, ADR-020 for Phase 6). **Matrix (L01)** adds **ADR-021** per `matrix-integration.md`.

---

## Quality Checks (orienting)

| Tool | Notes |
|------|-------|
| pytest | **309 passed** on reviewed tree after merge |
| ruff | Touched files clean in Phase 7; large pre-existing debt possible elsewhere |
| mypy | Pre-existing errors in some modules |

---

## Design Debt (carried forward)

1. Policy delegation batch UX (duplicate `tool_call_id` text).  
2. **Matrix** — implementation in progress (L01).  
3. Telegram inline confirmation for destructive tools.  
4. Artifact tools (`grep_artifact`, `list_artifacts`).  
5. aiosqlite pytest thread warnings (housekeeping).  

---

## Remaining roadmap

1. ~~Phase 7 cleanup~~  
2. **L01 Matrix** → **L02–L08** per [`kimi-phase-queue.md`](orchestration/kimi-phase-queue.md)  
3. Long-term: `docs/roadmap/future-systems-deferred-roadmap.md`  

---

## How to Use This File

### Claude / Cursor

1. Read at start of each Hestia session.  
2. After Kimi delivers work: update verdict, test counts, git state, `KIMI_CURRENT.md`; remove or acknowledge `.kimi-done`.  
3. Next Kimi cycle: follow **`KIMI_CURRENT.md`** (currently **L01 Matrix**).  

### Review checklist

1. Read `.kimi-done` and Kimi logs if present; read `docs/handoffs/` when applicable.  
2. `pytest tests/unit/ tests/integration/`  
3. New platform commands register tools and use async `respond_callback`  
4. Update this file  
