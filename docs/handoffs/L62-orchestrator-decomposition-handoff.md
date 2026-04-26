# L62 — Complete Orchestrator Decomposition

## Scope

Wire `TurnExecution` and `TurnFinalization` into `Orchestrator`, eliminating
~600 lines of duplicated logic from `engine.py`.

## Commits

| Commit | Description |
|--------|-------------|
| `refactor(orchestrator)` | Wire TurnExecution and TurnFinalization, thin engine.py to coordinator |
| `test(orchestrator)` | Update tool/confirmation tests, add delegation tests |

## Files changed

- `src/hestia/orchestrator/engine.py` — 913 → 305 lines
- `src/hestia/orchestrator/execution.py` — minor adjustments for wiring
- `src/hestia/orchestrator/finalization.py` — minor adjustments for wiring
- `tests/unit/test_orchestrator_concurrent_tools.py` — updated to test TurnExecution directly
- `tests/unit/test_orchestrator_confirmation_helper.py` — updated to test TurnExecution directly
- `tests/unit/test_orchestrator_delegation.py` — **new** mock-based delegation tests

## Acceptance

- [x] `engine.py` under 350 lines (305 achieved)
- [x] `TurnExecution` and `TurnFinalization` instantiated and called by `Orchestrator`
- [x] No duplicated logic between `engine.py` and phase classes
- [x] All tests pass (21 orchestrator tests)
