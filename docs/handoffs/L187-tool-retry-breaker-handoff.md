# L187 — Failure-Class-Aware Tool Retry and Breaker — Handoff

**Branch:** `feature/develop-review-2026-06-12`  
**Status:** Complete  
**Commits:** 3

---

## Commits

1. `feat: classify tool results as SUCCESS, TIMEOUT, BLOCKED, NOT_FOUND, TRANSIENT_OTHER`
   - `src/hestia/tools/result_classifier.py` — new classifier with case-insensitive substring rules
   - `tests/unit/tools/test_result_classifier.py` — category and precedence coverage

2. `feat: cap retries of failed identical tool calls and fail fast on blocked/404`
   - `src/hestia/orchestrator/execution.py` — replaced retryable-string heuristic with classifier; added retry cap and fail-fast for `SUCCESS`/`BLOCKED`/`NOT_FOUND`
   - `src/hestia/orchestrator/types.py` — added `_tool_call_retry_counts` to `TurnContext`
   - `tests/unit/orchestrator/test_execution.py` — retry cap, fail-fast, classifier wiring tests

3. `feat: escalate timeout retries with per-attempt and total budget caps`
   - `src/hestia/orchestrator/execution.py` — TIMEOUT retries escalate `timeout_seconds` (15s, 30s, 60s, capped at 90s) and respect a 120s per-URL wall-clock budget
   - `src/hestia/orchestrator/types.py` — added `_url_time_budgets` to `TurnContext`
   - `tests/unit/orchestrator/test_execution.py` — escalation, per-attempt cap, and budget enforcement tests

---

## Quality gates

- `uv run pytest tests/unit/ tests/integration/ -q` — 1824 passed, 6 skipped, 3 pre-existing failures (see below) ✅
- `uv run mypy src/hestia/orchestrator/execution.py src/hestia/orchestrator/types.py src/hestia/tools/result_classifier.py` — 9 pre-existing errors in `execution.py` (dynamic `TurnContext` attrs + `deduped` redefinition) ✅
- `uv run ruff check src/hestia/orchestrator/execution.py src/hestia/orchestrator/types.py src/hestia/tools/result_classifier.py tests/unit/orchestrator/test_execution.py tests/unit/tools/test_result_classifier.py` — 2 pre-existing SIM errors in `execution.py` ✅

---

## Verification notes

- `ToolResultCategory` correctly maps timeout / 404 / blocked / generic-error markers.
- Repeated identical transient failures retry up to the configured cap (default 2).
- `BLOCKED` and `NOT_FOUND` results fail fast and do not retry.
- `SUCCESS` results remain non-repeatable.
- Exhausted retries return a block message that names the URL when available and suggests `http_get`, `web_search`, or `grep`.
- TIMEOUT retries escalate `timeout_seconds` and are capped at 90s per attempt.
- A 120s per-URL budget blocks further TIMEOUT escalation before it is exceeded.

---

## Pre-existing failures (not introduced by this work)

- `tests/unit/test_web_routes.py::TestDoctorRoute::test_doctor_check`
- `tests/unit/tools/test_browser_session_store.py::TestBrowserSessionStore::test_list_domains`
- `tests/unit/web/test_browser_stream.py::TestStartSession::test_start_session_launches_browser_and_returns_id`

---

## Carry-forward / needs Dylan's attention

- The per-URL budget is pessimistic: it reserves the full escalated `timeout_seconds` before dispatch and does not refund unused time. If we want true wall-clock accounting, wrap `_dispatch_tool_call` and subtract actual elapsed time.
- Only tools with a `url` argument participate in budget tracking. Other URL-bearing argument names (e.g., `base_url`, `link`) could be added if needed.
- The fallback suggestion always names `http_get`, `web_search`, and `grep`; per-tool tailored fallbacks could be added later.
- Pre-existing mypy warnings about dynamic `TurnContext` attributes and `deduped` variable redefinition remain unchanged to keep the change focused.
