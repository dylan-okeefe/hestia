# Hestia L10 Report — 2026-04-13

**Loop:** L10 (orchestrator post-DONE fix + Matrix env/config parity + adapter robustness)  
**Branch:** `feature/l10-matrix-realworld-runtime`  
**Commit:** `1d31a89`  

---

## What changed

### Part A — Orchestrator post-`DONE` error handling (blocking bug)
- **File:** `src/hestia/orchestrator/engine.py`
- **Fix:** In the outer `except Exception` boundary of `process_turn`, if `turn.state` is already terminal (`DONE` or `FAILED`), the orchestrator now logs the delivery/persistence error and attempts a fallback `respond_callback` notification without attempting an illegal state transition.
- **Result:** `IllegalTransitionError: Cannot transition from done to failed` no longer crashes the turn when `respond_callback` (or post-DONE code) raises after the model has already produced a final answer.
- **Test:** Added `test_post_done_respond_callback_error_no_illegal_transition` in `tests/unit/test_orchestrator_errors.py`.

### Part B — Matrix operator experience
- **Config parity (`src/hestia/config.py`):**
  - Added `MatrixConfig.from_env()` classmethod that reads `HESTIA_MATRIX_HOMESERVER`, `HESTIA_MATRIX_USER_ID`, `HESTIA_MATRIX_DEVICE_ID`, `HESTIA_MATRIX_ACCESS_TOKEN`, and `HESTIA_MATRIX_ALLOWED_ROOMS` (comma-separated).
  - Documented runtime env vars in `docs/design/matrix-integration.md` §2.3.
- **Adapter robustness (`src/hestia/platforms/matrix_adapter.py`):**
  - `send_message` now raises `PlatformError` (instead of `RuntimeError`) on homeserver rejection.
  - `edit_message` now raises `PlatformError` on failure so the orchestrator’s `_update_status` catch block handles it consistently.
- **Tests:**
  - `tests/unit/test_config.py` — 3 new tests for `MatrixConfig.from_env`.
  - `tests/unit/test_matrix_adapter.py` — updated `RuntimeError` → `PlatformError` expectation and added `edit_message` error-response test.

---

## Test counts

```bash
uv run pytest tests/unit/ tests/integration/ -q
```

**Result:** 442 passed (baseline: 437 passed)

- +1 orchestrator regression test (post-DONE delivery error)
- +3 MatrixConfig env tests
- +1 Matrix adapter edit_message failure test

**Ruff:** No new issues introduced in touched files. Pre-existing lint debt in other modules left untouched.  
**mypy:** No new type errors introduced.

---

## Open risks / follow-ups for L11

- **B4 (optional smoke):** Deferred to L11 — no mock-inference `current_time` Matrix path test added in L10.
- **Full tool/memory Matrix coverage:** Explicitly out of scope for L10; scheduled for L11 per `KIMI_LOOPS_L10_L14.md`.
- **Live Matrix E2E:** Requires credentials collection (Dylan action before L12).

---

## Next loop

**L11** — `feature/l11-test-tools-memory-mock` (mock inference: every built-in tool + meta-tools + memory variants + teardown).
