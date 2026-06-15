# L187: Failure-Class-Aware Tool Retry and Breaker

## Goal
Make the repeated-identical-call breaker understand *why* a previous call failed and decide whether retrying is worthwhile, capped, and bounded.

## Motivation
During job-search runs, `browser_get_links` timed out on LinkedIn/Indeed and `http_get` on Built In Boston was blocked after one success. The current breaker treats every previous identical call as non-repeatable, so a transient timeout cannot be retried and a successful call blocks a genuinely different use. We need:
- Retry transient failures, but not forever.
- Fail fast on permanent failures (blocked, 404).
- Escalate strategy on repeated timeouts instead of hammering the same JS-rendered endpoint.

## Scope
- Add a tool-result classifier.
- Update the repeated-identical-call breaker in `src/hestia/orchestrator/execution.py`.
- Escalate timeout retries with increasing per-attempt timeouts and a total wall-clock budget per URL.
- After exhausting retries, return a tool result that tells the model to try a fallback strategy (`http_get`, `web_search`, `grep` artifact).
- Do NOT change trust/security policy behavior.

## Out of scope
- Automatic transparent fallback execution (e.g. silently swapping `browser_get` for `http_get`). The model chooses the fallback after reading the correction.
- Browser session reuse (L188).
- Chunked file writes (L218).

## §1 Add tool-result classifier

### Implementation
Create `src/hestia/tools/result_classifier.py`:

```python
from enum import Enum, auto

class ToolResultCategory(Enum):
    SUCCESS = auto()
    TIMEOUT = auto()
    BLOCKED = auto()      # 403, captcha, login wall, "Humans only", Cloudflare
    NOT_FOUND = auto()    # 404, page gone
    TRANSIENT_OTHER = auto()

def classify_tool_result(content: str, tool_name: str = "") -> ToolResultCategory:
    ...
```

Rules (case-insensitive substring matching):
- `timeout` / `timed out` → `TIMEOUT`
- `404`, `not found`, `page doesn't exist`, `page is gone`, `url returns 404` → `NOT_FOUND`
- `403`, `blocked`, `bot protection`, `cloudflare`, `captcha`, `humans only`, `login`, `sign in`, `unauthorized`, `access denied` → `BLOCKED`
- `error`, `failed`, `partial failure` → `TRANSIENT_OTHER`
- otherwise → `SUCCESS`

Move the existing `_is_retryable_tool_result` helper from `execution.py` to use this classifier: retryable categories are `TIMEOUT` and `TRANSIENT_OTHER`.

### Tests
Add `tests/unit/tools/test_result_classifier.py` with fixtures for each category and edge cases.

### Commit
`feat: classify tool results as SUCCESS, TIMEOUT, BLOCKED, NOT_FOUND, TRANSIENT_OTHER`

## §2 Retry cap and fail-fast in the repeated-call breaker

### Implementation
Update `_execute_tool_calls` in `src/hestia/orchestrator/execution.py`:
- Track retry count per tool-call key in the current turn (`ctx._tool_call_retry_counts: dict[_ToolCallKey, int]`).
- For a repeated key whose previous result was:
  - `SUCCESS`, `BLOCKED`, `NOT_FOUND` → block immediately (do not retry).
  - `TIMEOUT` or `TRANSIENT_OTHER` → allow retry only if `count < max_retries` (default 2).
- When `max_retries` is exhausted, block and return a message like:
  > "browser_get timed out N times for https://example.com. This URL is now DISABLED for the rest of this turn. Try http_get, web_search, or grep the cached artifact instead."
- The message should name the URL when available and suggest concrete fallback tools.

### Tests
Update `tests/unit/orchestrator/test_execution.py`:
- A failed identical call can be retried up to the cap.
- After the cap, it is blocked.
- A BLOCKED/NOT_FOUND result is not retried.
- A SUCCESS result is not retried.

### Commit
`feat: cap retries of failed identical tool calls and fail fast on blocked/404`

## §3 Timeout escalation with total budget

### Implementation
For `TIMEOUT` retries only:
- Increase the tool's `timeout_seconds` argument if it exists, using a schedule like 15s, 30s, 60s, capped at a maximum per-attempt timeout (e.g., 90s).
- Track a total wall-clock budget per URL in `ctx._url_time_budgets: dict[str, float]` (default budget 120s per URL across all tools in the turn).
- If the next escalation would exceed the total budget, skip the escalation and block immediately with the fallback suggestion.
- The budget should be keyed by normalized URL (strip query string? no, keep full URL; for search pages the query matters).

The timeout arg mutation should be applied to the retry tool call before dispatch.

### Tests
Add tests in `tests/unit/orchestrator/test_execution.py`:
- A TIMEOUT retry increases `timeout_seconds`.
- The per-attempt timeout is capped.
- The total budget is enforced (retry blocked before exceeding).

### Commit
`feat: escalate timeout retries with per-attempt and total budget caps`

## §4 Handoff
After all sections pass quality gates, update this file with any review carry-forward and write `docs/handoffs/L187-tool-retry-breaker-handoff.md`.

### Review carry-forward
- The per-URL budget is pessimistic: it reserves the full escalated `timeout_seconds` before dispatch and does not refund unused time. True wall-clock accounting would require timing the actual tool execution.
- Only tools with a `url` argument participate in budget tracking; other URL-bearing argument names are not budgeted.
- The fallback suggestion is generic (`http_get`, `web_search`, `grep`); per-tool tailored suggestions may be added later.
- Pre-existing mypy/ruff warnings in `src/hestia/orchestrator/execution.py` (dynamic `TurnContext` attributes, `deduped` redefinition, SIM102/SIM108) were left untouched to keep the change focused.

## Quality gates
Run after each section:
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Critical rules recap
- Do not merge or push without Dylan's okay.
- No trust/security policy changes.
- No new dependencies without asking.
- Restart `hestia-serve.service` after deploying to runtime.
