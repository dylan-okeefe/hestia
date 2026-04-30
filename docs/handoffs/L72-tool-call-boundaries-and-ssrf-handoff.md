# L72 — Tool Call Boundaries & SSRF Defense

## Intent & Meaning

This loop closes two boundary issues identified in the evaluation:

1. **Unbounded tool calls per turn:** `max_iterations` caps inference loops, but within a single iteration the model could request an unlimited number of tool calls. A malicious or confused prompt could trigger dozens of shell commands or HTTP requests in one batch.

2. **curl_cffi fallback weakens SSRF:** When `httpx` gets a 403 and `curl_cffi` is installed, the retry path does manual redirect validation instead of the `SSRFSafeTransport`. The pre-flight check alone does not prevent DNS rebinding. A weaker security path should require explicit opt-in.

## Changes Made

### §1 — Cap tool calls per turn

**`src/hestia/config.py`**
- Added `PolicyConfig.max_tool_calls_per_turn: int = 10`

**`src/hestia/orchestrator/engine.py`**
- `Orchestrator.__init__` accepts `max_tool_calls_per_turn` and passes it to `TurnExecution`

**`src/hestia/orchestrator/execution.py`**
- `TurnExecution.__init__` stores `max_tool_calls_per_turn`
- `_execute_tool_calls` truncates tool calls exceeding the cap. Excess calls receive error messages as tool results:
  ```
  "Tool call {name} was rejected: too many tool calls in this turn (limit: N)."
  ```

**`src/hestia/app.py`**
- `make_orchestrator` passes `max_tool_calls_per_turn=self.config.policy.max_tool_calls_per_turn`

### §2 — curl_cffi fallback becomes opt-in

**`src/hestia/config.py`**
- Added `HestiaConfig.use_curl_cffi_fallback: bool = False`

**`src/hestia/tools/builtin/http_get.py`**
- Extracted `_http_get_impl(url, timeout_seconds, use_curl_cffi)` with the fallback flag as an explicit parameter
- Added `make_http_get_tool(use_curl_cffi_fallback: bool = False)` factory
- The standalone `http_get` tool still exists (defaults to no fallback) for backward compatibility
- Updated docstring to reference the config field

**`src/hestia/tools/builtin/__init__.py`**
- Exported `make_http_get_tool`

**`src/hestia/app.py`**
- `make_app` registers `make_http_get_tool(cfg.use_curl_cffi_fallback)` instead of the bare `http_get` function

## Verification

- `pytest tests/unit/ tests/integration/ -q` → **1057 passed, 6 skipped**
- `ruff check` on changed files → **all checks passed**
- `mypy` on changed files → **no issues**

## Commit

```
feat(policy,http_get): cap tool calls per turn and make curl_cffi opt-in
```

## Risks & Follow-ups

- **None.** Both changes are strictly additive with safe defaults.
- The standalone `http_get` function is preserved for tests and direct imports. Only the app bootstrap path uses the factory.
