# L167 — Reasoning Guardrails & Parser Cleanup Handoff

**Status:** Complete  
**Branch:** `feature/l167-reasoning-guardrails`

## Summary

1. **Split XML fallback parser** (`src/hestia/core/inference.py`) into three named sub-parsers:
   - `_parse_json_tool_calls(text)` — Format 1: JSON inside `<tool_call>` tags
   - `_parse_adhoc_xml_tool_calls(text)` — Format 2: `<function=name> <parameter=key> value` XML
   - `_parse_glm_xml_tool_calls(text)` — Format 3: GLM-style `<arg_key>` / `<arg_value>` XML
   - `_extract_tool_calls_from_text(text)` now delegates to them in sequence and returns early on first match.
   - Fixed `args` variable reuse between Format 2 and Format 3 by giving each parser its own local variable (`adhoc_args`, `glm_args`).
   - Moved `_is_valid_url` to module level since both ad-hoc and GLM parsers need it.

2. **Added reasoning-length guardrail** (`src/hestia/orchestrator/execution.py`):
   - After storing the assistant message, if `reasoning_content` exceeds 1500 characters and there are no `tool_calls` or `content`, the orchestrator sends:
     > "🛑 You have been reasoning extensively but haven't emitted a tool call. Please make a tool call now."
   - Increments `turn.iterations` and continues the loop, giving the model another chance to act.

3. **Verified MemoryStore.list_memories filtering** (`src/hestia/memory/store.py`):
   - Method already accepts `platform` and `platform_user` parameters.
   - SQL query already filters by these fields via `_resolve_scope` + `where_clauses`.
   - Existing tests in `tests/unit/test_memory_user_scope.py` verify the filter (`test_list_memories_filters_by_user`, `test_cross_user_access_blocked`).
   - No code changes needed.

4. **Documented context_length relationship** (`config.runtime.py`):
   - Verified `context_length=32768` matches `deploy/hestia-llama.service` `--ctx-size 32768`.
   - Updated comment to explain that with `--parallel 4`, each slot gets 8192 tokens, and the policy engine uses this value for context-window budgeting.

## Quality gates

- `pytest tests/unit/test_memory_store.py tests/unit/test_memory_user_scope.py tests/unit/test_inference_client.py tests/unit/orchestrator/test_execution.py -k "not test_call_tool_not_in_dispatch_table"` — **51 passed, 1 deselected**
- `mypy src/hestia/core/inference.py src/hestia/orchestrator/execution.py` — **clean**
- `ruff check src/hestia/core/inference.py src/hestia/orchestrator/execution.py` — **clean**
- Pre-existing failures in broader suite unchanged (`test_search_web_duckduckgo.py`, `test_web_auth.py`, `test_sessions.py`, `test_orchestrator.py`, etc.)

## Commits

- `refactor(inference): split XML fallback parser into named sub-parsers`
- `feat(orchestrator): add reasoning-length action-forcing guardrail`
- `docs(config): clarify context_length vs llama-server -c flag relationship`
