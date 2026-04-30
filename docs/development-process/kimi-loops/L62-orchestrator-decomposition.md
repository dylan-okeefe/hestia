# L62 — Complete Orchestrator Decomposition

**Status:** Outline spec. Branch from `develop`.

**Branch:** `feature/l62-orchestrator-decomposition`

## Goal

Wire `TurnExecution` and `TurnFinalization` into `Orchestrator` so the phase
classes are actually used, eliminating ~1,200 lines of duplicated logic.

Full detail in:
`docs/development-process/reviews/docs-and-code-overhaul-april-26.md` Part 2.3.

## Scope

### §1 — Wire TurnExecution

- Replace `Orchestrator._run_inference_loop` with delegation to
  `TurnExecution.run()`
- Delete parallel private methods from `engine.py`:
  `_execute_tool_calls`, `_execute_policy_delegation`, `_check_confirmation`,
  `_dispatch_tool_call`, `_scan_tool_result`
- Ensure `TurnExecution` has everything it needs (imports, dependencies)

### §2 — Wire TurnFinalization

- Replace `Orchestrator._finalize_turn` with delegation to
  `TurnFinalization.finalize()`
- Delete parallel finalization logic from `engine.py`

### §3 — Thin engine.py to ~300 lines

- After §1–§2, audit remaining `engine.py` responsibilities
- Move anything that doesn't belong in the coordinator to appropriate modules
- Target: ~300-line coordinator that delegates to Assembly, Execution, Finalization

### §4 — Tests

- Ensure all existing orchestrator tests pass
- Add tests verifying `Orchestrator` delegates to phase classes (mock-based)

## Acceptance

- `engine.py` under 350 lines
- `TurnExecution` and `TurnFinalization` are actually instantiated and called
- No duplicated logic between `engine.py` and phase classes
- All tests pass

## Dependencies

L61 (bug fixes) should merge first — `TransitionCallback` move affects imports.
