# L168 — Variable Interpolation & Webhook Route Extraction Handoff

**Status:** Complete  
**Branch:** `feature/l168-variable-interpolation`

## Summary

1. **Variable interpolation engine** (`src/hestia/workflows/interpolation.py`):
   - `VAR_RE` compiles `{{key}}` or `{{node_id.field}}` syntax.
   - `interpolate(template, context)` replaces placeholders with values from a nested dict context.
   - Missing keys, non-dict intermediates, and `None` values all resolve to empty strings.

2. **Integrated interpolation into workflow nodes**:
   - `SendMessageNode` (`src/hestia/workflows/nodes/send_message.py`): interpolates `text` after resolution, before sending.
   - `LLMDecisionNode` (`src/hestia/workflows/nodes/llm_decision.py`): interpolates `prompt_template` after reading from config, before building the LLM prompt.

3. **Extracted webhook routes** (`src/hestia/web/routes/webhooks.py`):
   - Moved `POST /api/webhooks/{endpoint}` (`receive_webhook`) out of `workflows.py` into its own router module.
   - Registered the new router in `src/hestia/web/api.py` with `prefix="/api"`.
   - Removed `hashlib`, `hmac`, `json`, `datetime` imports from `workflows.py` that were only used by the webhook endpoint.
   - No behavior changes; the endpoint logic is identical.

4. **Public `is_rate_limited()` method** (`src/hestia/web/auth.py`):
   - Added `AuthManager.is_rate_limited(ip: str) -> bool` as a public wrapper around `_is_rate_limited`.
   - Updated `src/hestia/web/routes/auth.py` to call the public method.
   - Updated `tests/unit/test_web_auth.py` rate-limit boundary tests to use the public method.

5. **UI live preview** — **SKIPPED**.
   - The React node components (`SendMessageNode.tsx`, `LLMDecisionNode.tsx`) are thin ReactFlow renderers with no edit-time state or mock-data infrastructure. Adding a live preview would require significant wiring (mock context propagation, interpolation logic in TS, UI state). Deferred per instructions: the backend interpolation engine is the critical piece.

## Quality gates

- `pytest tests/unit/workflows/test_interpolation.py` — **7 passed**
- `pytest tests/unit/workflows/test_webhook_auth.py tests/unit/test_web_routes.py` — **71 passed**
- `mypy src/hestia/workflows/interpolation.py src/hestia/web/routes/webhooks.py src/hestia/web/routes/workflows.py src/hestia/web/api.py src/hestia/web/auth.py src/hestia/web/routes/auth.py src/hestia/workflows/nodes/send_message.py src/hestia/workflows/nodes/llm_decision.py` — **clean**
- `ruff check` on all changed files — **clean** (2 pre-existing issues in untouched lines of `auth.py` and `auth/routes.py` remain)
- Pre-existing failures unchanged (`test_search_web_duckduckgo.py` collection error, `test_web_auth.py`/`test_sessions.py` fixture errors)

## Commits

- `feat(workflows): add {{variable}} interpolation engine`
- `feat(workflows): integrate interpolation into SendMessageNode and LLMDecisionNode`
- `refactor(api): extract webhook routes into dedicated webhooks.py`
- `refactor(auth): add public is_rate_limited() method to AuthManager`
