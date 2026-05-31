# L205 — Checkpoint & Rollback — Handoff

**Branch:** `feature/l205-checkpoint-and-rollback`  
**Status:** Complete  
**Commits:** 4

---

## Commits

1. `feat(tools): add per-turn checkpoint manager`
   - `src/hestia/tools/checkpoint.py` — `Checkpoint` dataclass, `CheckpointManager` with git-aware stash fallback to file-copy

2. `feat(orchestrator): wire checkpoint create/restore into turn lifecycle`
   - `src/hestia/config.py` — added `checkpoint_on_edit`, `auto_rollback_on_failure` to `TrustConfig`; `checkpoint_scope` to `StorageConfig`
   - `src/hestia/orchestrator/engine.py` — creates checkpoint at turn start
   - `src/hestia/orchestrator/finalization.py` — discards on DONE, restores on FAILED when `auto_rollback_on_failure=True`
   - `src/hestia/app.py` — instantiates shared `CheckpointManager`

3. `feat(tools): add rollback_turn builtin`
   - `src/hestia/tools/builtin/rollback.py` — `rollback_turn(turn_id)` tool
   - `src/hestia/runtime_context.py` — added `current_turn_id` context var

4. `test(tools): add checkpoint create/restore/discard tests`
   - `tests/unit/tools/test_checkpoint.py` — 8 tests: create, restore content/tree, discard, idempotency, unknown turn, SHA-256

---

## Quality gates

- `pytest tests/unit/tools/test_checkpoint.py` — 8 passed ✅
- `mypy` on modified files — 0 errors ✅
- `ruff check` on modified files — all passed ✅

---

## Verification notes

- Checkpoint captures file state at turn start
- Restore reverts file content and directory tree changes
- `rollback_turn` tool is available and functional
- Auto-rollback only fires when `auto_rollback_on_failure=True`

---

## Next loop

L206 — Matrix Auth Code Delivery (deferred, test-only, lowest priority)
