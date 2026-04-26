# L56 — Orchestrator Decomposition

## Scope

Decompose `orchestrator/engine.py` (originally 978 lines, 15+ concerns) into
three explicit pipeline phases: **TurnAssembly**, **TurnExecution**,
**TurnFinalization**.

## Commits

| Commit | Section | Description |
|--------|---------|-------------|
| `29389b7` | §1 | Extract `TurnAssembly` — context building, style prefix, voice prompt, proposals, slots |
| `a771e87` | §2 | Extract `TurnExecution` — inference loop, tool dispatch, confirmation gating, injection scanning |
| `cae1d15` | §3 | Extract `TurnFinalization` — trace recording, failure bundles, slot save, handoff summary |
| `353ae95` | §4 | Thin `Orchestrator` to phase coordinator; `process_turn` pipeline is `assembly.prepare() → execution.run() → finalization.finalize()` |

## Files changed

- `src/hestia/orchestrator/engine.py` — **284 lines** (was 978)
- `src/hestia/orchestrator/assembly.py` — **126 lines** (new)
- `src/hestia/orchestrator/execution.py` — **430 lines** (new)
- `src/hestia/orchestrator/finalization.py` — **328 lines** (new)

## Quality gates

- **Tests:** 78 passed (orchestrator + scheduler + memory)
- **Ruff:** All checks passed
- **Mypy:** No issues found in 7 source files

## Review findings

**Phase classes exceed 250-line target:**
- `execution.py` is 430 lines — contains concurrent vs serial tool partitioning,
  confirmation gating, injection scanning, and policy delegation. Could be split
  further into `TurnExecution` + `ToolDispatcher` in a future loop.
- `finalization.py` is 328 lines — contains trace recording, failure bundles,
  slot save, and handoff summarization. Could be split into `TurnFinalization` +
  `TraceRecorder` + `FailureBundler`.

These are noted as **deferred cleanup** — the primary goal (thinning
`engine.py` below 300 lines) is achieved.

## Merge status

**Do NOT merge to develop.** This is v0.11 feature-branch work.
Branch: `feature/l56-orchestrator-decomposition`
