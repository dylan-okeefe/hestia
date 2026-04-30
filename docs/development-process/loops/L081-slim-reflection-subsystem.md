# L81 — Slim Reflection Subsystem

**Status:** Spec only  
**Branch:** `feature/l81-slim-reflection-subsystem` (from `develop`)

## Goal

Cut the reflection subsystem from ~752 lines to ≤350 lines without losing capability. The subsystem works correctly but carries disproportionate weight for an opt-in feature.

## Review carry-forward

- *(none — this is a clean-up loop)*

## Scope

### §1 — Audit and identify cuts

Current reflection files:
- `runner.py` (272 lines) — three-pass pipeline (pattern mining → proposal generation → queue write). Likely over-verbose prompt assembly and repetitive error handling.
- `store.py` (192 lines) — ProposalStore with full CRUD. Could be simplified if some methods are unused.
- `scheduler.py` (144 lines) — ReflectionScheduler wiring.
- `types.py` (70 lines) — Observation, Proposal dataclasses.
- `prompts.py` (61 lines) — Prompt templates.
- `__init__.py` (13 lines)

**Audit questions:**
- Does `runner.py` need a full three-pass pipeline, or can it be two-pass (mine + generate)?
- Are all ProposalStore methods hit by CLI commands, or is there dead CRUD?
- Can `prompts.py` be inlined into `runner.py` to save a module?
- Is the `Observation` type adding value, or can it be a simple dict?

**Commit:** `docs(reflection): audit findings and cut list`

### §2 — Consolidate runner pipeline

Collapse the three-pass pipeline into a single `ReflectionRunner.run_once()` method that:
1. Reads recent trace/failure data
2. Generates proposals via inference
3. Writes proposals to store

Remove intermediate abstraction layers. Inline `prompts.py` content. Remove `Observation` type if it doesn't cross module boundaries.

**Target:** `runner.py` ≤120 lines.

**Commit:** `refactor(reflection): consolidate three-pass pipeline into single run_once`

### §3 — Simplify ProposalStore

Audit which store methods are actually called by CLI commands and the runner. Remove unused methods. If the store is only doing insert/list/get-by-id, the SQL can be simplified.

**Target:** `store.py` ≤80 lines.

**Commit:** `refactor(reflection): remove dead CRUD from ProposalStore`

### §4 — Slim scheduler and types

If `Observation` is removed, update `types.py`. Merge `prompts.py` into `runner.py` and delete the module. Simplify `scheduler.py` if it has boilerplate.

**Target:** `scheduler.py` ≤80 lines, `types.py` ≤30 lines.

**Commit:** `refactor(reflection): merge prompts into runner, slim scheduler`

## Tests

- Keep `tests/unit/test_reflection*.py` and `tests/integration/test_reflection*.py` green.
- If test coverage drops because code was deleted, that's acceptable — the remaining code must still be covered.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `find src/hestia/reflection/ -name "*.py" | xargs wc -l` total ≤ 350
- `.kimi-done` includes `LOOP=L81`

## Handoff

- Write `docs/handoffs/L81-slim-reflection-subsystem-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to next queued item (or idle)
