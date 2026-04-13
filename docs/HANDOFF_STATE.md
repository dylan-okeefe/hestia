# Hestia — Review & Orchestration State

> **Purpose:** Handoff contract between Claude (Cowork) and Cursor for reviewing Kimi's output and orchestrating the next phase.
>
> **Last updated:** 2026-04-12
> **Last updated by:** Cursor (L04 merged; L05 Phase 10 next)

---

## Kimi — dispatch (pick one)

### A — One-shot CLI (preferred when `kimi` supports `--prompt`)

From the repo root:

```bash
chmod +x scripts/kimi-run-current.sh   # once
./scripts/kimi-run-current.sh > .kimi-output.log 2>&1
```

The script defaults to **`--quiet`** (final assistant message only; see Kimi docs). For full output: `KIMI_VERBOSE=1 ./scripts/kimi-run-current.sh` or pass **`--print`** explicitly. Other Kimi flags go after the script name.

**Watch progress without quiet-mode stdout:** in a **second** terminal, tail Kimi’s debug log (Kimi CLI writes here when **`--debug`** is on):

```bash
# Terminal 1 — enables Kimi --debug (still uses --quiet unless you override)
KIMI_DEBUG=1 ./scripts/kimi-run-current.sh >> .kimi-output.log 2>&1

# Terminal 2 — live trace (path is per Kimi docs)
tail -f ~/.kimi/logs/kimi.log
```

Optional: `tail -f .kimi-output.log` only captures the thin wrapper stream (mostly empty under `--quiet`).

**Completion signal:** wait until **`./scripts/kimi-run-current.sh` exits**, then confirm **`.kimi-done`** exists and read it before review.

### B — Interactive Kimi (fallback)

Kimi is running in `~/Hestia`. Send **one** message:

```text
Read docs/prompts/KIMI_CURRENT.md, then execute the full "Current task" section including every linked file under docs/design/. Finish with the handoff steps and .kimi-done artifact described in the active loop spec.
```

**Single source of truth for "what Kimi does next":** [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md). After each Kimi cycle, **Cursor** updates that file and this section.

### Orchestration loop (Cursor — full autonomous chain)

Dylan can **defer per-loop review** to Cursor for a **queued multi-loop run** (see [`kimi-phase-queue.md`](orchestration/kimi-phase-queue.md)): Cursor reviews, updates the **next** loop’s **`## Review carry-forward`**, advances `KIMI_CURRENT.md`, and **starts the next `./scripts/kimi-run-current.sh`** until the queue is finished or blocked. Dylan gets **short chat summaries** between loops and does a **single** pass when everything is done (plus normal `git push`).

1. **Wait for done:** Kimi CLI exits **and** `.kimi-done` exists with `HESTIA_KIMI_DONE=1` (or read `.kimi-output.log` if Kimi was redirected).
2. **Review:** diff (`develop..HEAD` or merge base), handoff notes, `uv run pytest tests/unit/ tests/integration/ -q`.
3. If issues → add a follow-up design section or a tight `KIMI_PHASE_*_FOLLOWUP*.md`; point `KIMI_CURRENT.md` at it **or** re-run Kimi on the same loop after fixing carry-forward (Cursor may fix trivial issues directly).
4. If green → merge per gitflow, update this file, set `KIMI_CURRENT.md` for the next queue row in [`docs/orchestration/kimi-phase-queue.md`](orchestration/kimi-phase-queue.md). **Before** the next Kimi run, edit that **next** loop spec under [`docs/orchestration/kimi-loops/`](orchestration/kimi-loops/) and add or extend a **`## Review carry-forward`** section with every bug, code smell, or nit discovered in review (even small ones), so Kimi addresses them in the same pass as the main scope.
5. Remove stale **`.kimi-done`** before the next Kimi launch (the helper script does this automatically).
6. **Loop log:** After each review (and whenever you set the next prompt), append a **dated** section to [`docs/orchestration/kimi-loop-log.md`](orchestration/kimi-loop-log.md) with the full narrative. In the **Cursor chat**, reply with only a **brief** bullet summary of the same loop instance.
7. **Start the next loop:** run `./scripts/kimi-run-current.sh` again from repo root (same as §A) unless the queue has no further rows or Kimi is blocked — then tell Dylan the run is complete and what to push.

---

## Current branch and phase

- **Branch:** `develop` (local **ahead of** `origin/develop` until you `git push` — includes Phase 7 cleanup + orchestration docs)
- **Phase 7:** **Merged** — commit **`265003b`** on `develop` ("fix: phase 7 cleanup — bugs, security, dead code").
- **Active Kimi work:** **L05 Phase 10** (memory epochs) — [`docs/orchestration/kimi-loops/L05-phase-10-memory-epochs.md`](orchestration/kimi-loops/L05-phase-10-memory-epochs.md). Pointer: [`docs/prompts/KIMI_CURRENT.md`](prompts/KIMI_CURRENT.md).

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
3. ~~**L01 Matrix adapter**~~ — Done (`c3c34b2` on `develop`)  
4. ~~**L02 Phase 8a**~~ — Done (`98b4caa` on `develop`)  
5. ~~**L03 Phase 8b**~~ — Done (`0034038` on `develop`)  
6. ~~**L04 Phase 9**~~ — Done (`39caca5` on `develop`)  
7. **L05 Phase 10** — memory epochs (`L05-phase-10-memory-epochs.md`)  
8. **L06–L08** — remainder per queue table  

**Earlier prompts (reference only):**

- [`KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md`](prompts/KIMI_PHASE_6_CLOSEOUT_AND_GITFLOW.md) — closeout spec (completed)  
- [`KIMI_PHASE_6_FOLLOWUP_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_PROMPT.md)  
- [`KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md`](prompts/KIMI_PHASE_6_FOLLOWUP_REVIEW_FIXES_PROMPT.md)  
- [`kimi-hestia-phase-7-cleanup.md`](design/kimi-hestia-phase-7-cleanup.md) — Phase 7 spec (completed)  

---

## Git state

| Branch | Role |
|--------|------|
| `develop` | **Tip** — through **L04** Phase 9 (`39caca5`); not yet pushed |
| `feature/phase-9-test-infra` | Merged into `develop` |
| `feature/phase-8b-cli-exceptions-datetime` | Merged into `develop` |
| `feature/matrix-adapter` | Merged into `develop` (historical) |
| `feature/phase-7-cleanup` | Historical |
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
| Last `pytest tests/unit/ tests/integration/ -q` on `develop` after L04 merge (2026-04-12) | **379 passed** |

Run: `uv run pytest tests/unit/ tests/integration/ -q`

---

## Architecture Decisions (ADRs)

21 ADRs through **ADR-022** (identity, L02). **L05** should add **ADR-023** (memory epochs) per roadmap §10.1.

---

## Quality Checks (orienting)

| Tool | Notes |
|------|-------|
| pytest | **379 passed** on reviewed tree after L04 merge |
| ruff | Touched files clean in Phase 7; large pre-existing debt possible elsewhere |
| mypy | Pre-existing errors in some modules |

---

## Design Debt (carried forward)

1. Policy delegation batch UX (duplicate `tool_call_id` text).  
2. ~~**Matrix**~~ — L01 landed; further Matrix work in Phase 9 e2e.  
3. Telegram inline confirmation for destructive tools.  
4. Artifact tools (`grep_artifact`, `list_artifacts`).  
5. aiosqlite pytest thread warnings (housekeeping).  

---

## Remaining roadmap

1. ~~Phase 7 cleanup~~  
2. ~~**L01 Matrix**~~  
3. **L05–L08** per [`kimi-phase-queue.md`](orchestration/kimi-phase-queue.md)  
4. Long-term: `docs/roadmap/future-systems-deferred-roadmap.md`  

---

## How to Use This File

### Claude / Cursor

1. Read at start of each Hestia session.  
2. After Kimi delivers work: update verdict, test counts, git state, `KIMI_CURRENT.md`; remove or acknowledge `.kimi-done`.  
3. Next Kimi cycle: follow **`KIMI_CURRENT.md`** (currently **L05 Phase 10**).  

### Review checklist

1. Read `.kimi-done` and Kimi logs if present; read `docs/handoffs/` when applicable.  
2. `pytest tests/unit/ tests/integration/`  
3. New platform commands register tools and use async `respond_callback`  
4. Update this file  
