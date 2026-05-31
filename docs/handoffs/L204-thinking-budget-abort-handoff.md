# L204 — Thinking Budget Abort — Handoff

**Branch:** `feature/l204-thinking-budget-abort`  
**Status:** Complete  
**Commits:** 3

---

## Commits

1. `feat(orchestrator): add mid-stream thinking-budget abort`
   - `src/hestia/errors.py` — added `ThinkingBudgetExceededError`
   - `src/hestia/orchestrator/types.py` — added `thinking_aborted: bool = False` to `Turn`
   - `src/hestia/orchestrator/execution.py` — thinking-char counter in `_run_inference_streaming()`, raises on budget breach

2. `feat(orchestrator): inject commit nudge on thinking-budget abort`
   - `src/hestia/orchestrator/execution.py` — catches `ThinkingBudgetExceededError`, transitions to `RETRYING`, sets `reasoning_budget=0`, appends commit nudge system message

3. `test(orchestrator): add thinking-budget abort behavioral tests`
   - `tests/unit/test_orchestrator_streaming.py` — 6 tests: abort retries, within budget completes, abort limit enforced

---

## Quality gates

- `pytest tests/unit/test_orchestrator_streaming.py` — 6 passed ✅
- `mypy` on modified files — 0 errors ✅
- `ruff check` on modified files — 0 new issues ✅

---

## Verification notes

- Stream exceeding thinking budget is aborted and retried with commit nudge
- Stream within budget completes normally
- Only one thinking-abort per turn enforced

---

## Next loop

L205 — Checkpoint & Rollback (T1.5b)
