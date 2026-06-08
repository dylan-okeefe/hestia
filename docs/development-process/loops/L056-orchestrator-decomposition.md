# L56 — Orchestrator Decomposition

**Status:** Outline spec. Feature branch work; do **not** merge to `develop`
until v0.11 release-prep.

**Branch:** `feature/l56-orchestrator-decomposition` (from `develop`)

## Goal

Decompose `orchestrator/engine.py` (982 lines, 15+ concerns) into three explicit
pipeline phases: **TurnAssembly**, **TurnExecution**, **TurnFinalization**.

## Scope

### §1 — TurnAssembly

Extract from `Orchestrator`:
- Context building coordination (`_prepare_turn_context`)
- Style prefix injection
- Voice mode system prompt injection
- Proposal store peek
- Slot acquisition / slot-save-path setup

### §2 — TurnExecution

Extract from `Orchestrator`:
- The `_run_inference_loop` method
- Tool dispatch (`_execute_tool_calls`)
- Concurrent vs serial tool partitioning
- Confirmation gating
- Injection scanning
- Policy delegation (reasoning budget, etc.)

### §3 — TurnFinalization

Extract from `Orchestrator`:
- Trace recording
- Failure bundle recording
- Slot save
- Handoff summarization
- Error sanitization

### §4 — Orchestrator becomes a thin coordinator

The `Orchestrator` class wires the three phases together. It keeps:
- Session store reference
- Inference client reference
- Policy engine reference
- The public `process_turn()` entry point

## Tests

- All existing orchestrator tests must pass without modification.
- New tests for each phase class in isolation (mock stores/clients).

## Acceptance

- `orchestrator/engine.py` under 300 lines.
- Each phase class under 250 lines.
- `mypy` and `pytest` green.
- No behavioral changes — pure decomposition.

## Handoff

- Write `docs/handoffs/L56-orchestrator-decomposition-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Do NOT merge to develop until release-prep.

## Dependencies

- L55 (TurnContext.session non-optional) makes this cleaner.
