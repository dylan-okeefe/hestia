# L196 — Orchestrator & Inference Robustness — Handoff

**Branch:** `feature/l196-orchestrator-and-inference-robustness`  
**Status:** Complete  
**Commits:** 5

---

## Commits

1. `fix(orchestrator): align streaming malformed-arg handling with chat()` (M1)
   - `src/hestia/orchestrator/execution.py` — streaming tool-call buffer now logs warning and skips non-dict args instead of raising `InferenceServerError`

2. `fix(orchestrator): route IllegalTransitionError to FAILED with user notice` (M6)
   - `src/hestia/orchestrator/engine.py` — catches `IllegalTransitionError`, forces `TurnState.FAILED`, sends user-facing message via `respond_callback`
   - `tests/unit/test_orchestrator_errors.py` — added `test_illegal_transition_results_in_failed_and_user_notice`

3. `refactor(inference): use logger instead of print for malformed tool-call warnings` (M7)
   - `src/hestia/core/inference.py` — replaced `print()` with `logger.warning()` in tool-call parsing

4. `refactor(inference): defensive dict access in tool-call parsing` (L4)
   - `src/hestia/core/inference.py` — replaced direct dict indexing with `.get()` and graceful skip logic for missing `message`, `function`, `arguments`, `name`, `id` fields

5. `fix(orchestrator): remove unused InferenceServerError import after M1 fix`
   - `src/hestia/orchestrator/execution.py` — cleaned up unused import

---

## Quality gates

- `pytest tests/unit/test_orchestrator_errors.py tests/unit/test_inference_client.py` — 13 passed ✅
- `mypy src/hestia/core/inference.py src/hestia/orchestrator/engine.py src/hestia/orchestrator/execution.py` — 0 errors ✅
- `ruff check` — 0 new issues (2 pre-existing E501 in execution.py) ✅

---

## Verification notes

- Streaming path now skips malformed JSON args (matches non-streaming `chat()`)
- Illegal transitions result in `FAILED` state + user-visible error message
- Malformed tool-call warnings use logger (controllable, not stdout)
- Missing fields in inference responses are skipped gracefully

---

## Next loop

L197 — Web & Auth Hardening (M3, M8, M5)
