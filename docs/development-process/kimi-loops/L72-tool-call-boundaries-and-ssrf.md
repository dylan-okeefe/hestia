# L72 — Tool Call Boundaries & SSRF Defense

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l72-tool-call-boundaries-and-ssrf` (from `develop`)

## Goal

Cap the number of tool calls a model can request in a single turn, and close the SSRF protection gap in the curl_cffi fallback path.

---

## Intent & Meaning

The evaluation identified two boundary issues:

1. **Unbounded tool calls per turn:** `max_iterations` caps inference loops, but within a single iteration the model can request an unlimited number of tool calls. `_execute_tool_calls` partitions into serial/concurrent but does not limit the total count. A malicious or confused prompt could trigger dozens of shell commands or HTTP requests in one batch.

2. **curl_cffi fallback weakens SSRF:** When `httpx` gets a 403 and `curl_cffi` is installed, the retry path does manual redirect validation via `_is_url_safe()` instead of the `SSRFSafeTransport`. The pre-flight check alone does not prevent DNS rebinding (resolve at check time, different IP at connect time). The code even notes this limitation.

The intent is **defense in depth at the boundary**. Hestia trusts the model to choose tools wisely, but it should not trust the model to choose *how many*. A cap is a cheap guardrail that prevents accidental or adversarial denial-of-service (to the operator's machine, to external APIs, or to the llama-server). The SSRF intent is simpler: the fallback path should not be weaker than the primary path. If `curl_cffi` cannot use `SSRFSafeTransport`, it should not be automatic.

---

## Scope

### §1 — Cap tool calls per turn

**File:** `src/hestia/orchestrator/execution.py`
**Evaluation:** No rate limiting on tool calls per turn.

**Change:**
Add a `max_tool_calls_per_turn` config field (default: 10) to `TrustConfig` or `PolicyConfig`. In `_execute_tool_calls`, if `len(tool_calls) > max_tool_calls_per_turn`, reject the excess with a `ToolCallResult` containing an error message, or raise a `PolicyFailureError`.

```python
if len(tool_calls) > self._max_tool_calls_per_turn:
    logger.warning("Model requested %d tool calls; capping at %d", len(tool_calls), self._max_tool_calls_per_turn)
    # Option A: truncate and inform
    # Option B: fail the turn
```

**Intent:** A model that goes off the rails and requests 50 tool calls should hit a wall, not a conveyor belt.

**Commit:** `feat(policy): cap tool calls per turn`

---

### §2 — curl_cffi fallback becomes opt-in

**File:** `src/hestia/tools/builtin/http_get.py`
**Evaluation:** The curl_cffi retry path is documented as weaker but automatic.

**Change:**
- Add a config flag `use_curl_cffi_fallback: bool = False` to `HttpConfig` (or `HestiaConfig`).
- Only attempt the curl_cffi path if the flag is explicitly enabled.
- Update the code comment to reference the config field.

**Intent:** A weaker security path should require explicit opt-in, not automatic fallback. Operators who need curl_cffi for specific sites should turn it on knowingly.

**Commit:** `fix(http_get): make curl_cffi fallback opt-in`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `max_tool_calls_per_turn` exists in config and is enforced.
- `curl_cffi` fallback only runs when explicitly enabled.
- All tests pass.

## Acceptance (Intent-Based)

- **A runaway model is contained.** A synthetic test with 100 mocked tool calls should result in at most `max_tool_calls_per_turn` executions.
- **The weaker HTTP path is not the default.** A fresh config with no changes should never use curl_cffi.
- **The operator knows they are using curl_cffi.** The config field name should make the trade-off obvious.

## Handoff

- Write `docs/handoffs/L72-tool-call-boundaries-and-ssrf-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l72-tool-call-boundaries-and-ssrf` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
