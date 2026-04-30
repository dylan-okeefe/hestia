# L056b: CliAppContext Decomposition

**Status:** Complete — merged to `feature/v0.10.1-pre-publication-prep`  
**Branch:** `feature/v0.10.1-pre-publication-prep`  
**Scope:** Split the 18-param God Object into CoreAppContext + FeatureAppContext, refactor make_app to phased startup.

---

## Design

### Problem
`CliAppContext` has 18 constructor parameters, does config + stores + lazy init + orchestrator factory + DB bootstrap + injection scanner factory. `make_app` is 120 lines of imperative wiring that instantiates every feature regardless of `enabled`.

### Solution
1. **Extract `CoreAppContext`** — always-available subsystems: config, db, session_store, tool_registry, policy, memory_store, failure_store, trace_store, artifact_store, confirm_callback, calibration_path, compiled_identity, verbose. Lazy properties: inference, context_builder, slot_manager.
2. **Extract `FeatureAppContext`** — optional subsystems: scheduler_store, skill_store, proposal_store, style_store, style_builder, epoch_compiler, skill_index_builder. Lazy properties: reflection_scheduler, style_scheduler, handoff_summarizer.
3. **Keep `CliAppContext` as the public facade** — delegates to `_core` and `_features` via properties. CLI command signatures don't change.
4. **Refactor `make_app`** — phased startup: core first (unconditional), features conditional on config flags.

### Phased startup in make_app

```
Phase 1: Core (always)
  - Database, session store, policy, memory store
  - Tool registry with built-in tools
  - Failure store, trace store, artifact store
  - Identity compilation

Phase 2: Features (conditional)
  - Scheduler store (if config.scheduler.enabled)
  - Reflection/proposal store (if config.reflection.enabled)
  - Style store/builder (if config.style.enabled)
  - Skill store/index (if HESTIA_EXPERIMENTAL_SKILLS)
  - Epoch compiler (if config.memory_epochs.enabled)
```

---

## Files touched

- `src/hestia/app.py` — CoreAppContext, FeatureAppContext, refactored make_app
- `src/hestia/cli.py` — no signature changes (CliAppContext remains the public type)

---

## Test Plan

- `uv run pytest tests/ -q` — no regressions
- `uv run mypy src/hestia/app.py` — type clean
