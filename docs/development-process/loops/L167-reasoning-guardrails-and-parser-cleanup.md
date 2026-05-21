# L167 — Reasoning Guardrails & Parser Cleanup

**Status:** Spec only  
**Branch:** `feature/l167-reasoning-guardrails-and-parser-cleanup` (from `feature/workflow-builder-runtime`)  
**Depends on:** L163 (repo hygiene)

## Intent

The runtime branch review identified three medium-priority inference issues:

1. `_extract_tool_calls_from_text` is 146 lines with three regex-heavy parsing paths — hard to maintain.
2. The model burns its output token budget reasoning instead of acting. An orchestrator-level guardrail could detect this and force action.
3. `MemoryStore.list_memories` may not filter by platform/platform_user, causing memory leakage between users.

## Review carry-forward

- *(none)*

## Scope

### §1 — Split XML fallback parser into named functions

In `src/hestia/core/inference.py`, refactor `_extract_tool_calls_from_text`:

```python
def _parse_json_tool_calls(text: str) -> list[ToolCall]:
    """Format 1: JSON inside <tool_call> tags."""
    ...

def _parse_adhoc_xml_tool_calls(text: str) -> list[ToolCall]:
    """Format 2: <function=name> <parameter=key> value XML."""
    ...

def _parse_glm_xml_tool_calls(text: str) -> list[ToolCall]:
    """Format 3: GLM-style <arg_key>/<arg_value> XML."""
    ...

def _extract_tool_calls_from_text(text: str) -> list[ToolCall]:
    for parser in (_parse_json_tool_calls, _parse_adhoc_xml_tool_calls, _parse_glm_xml_tool_calls):
        results = parser(text)
        if results:
            return results
    return []
```

Also fix the `args` variable reuse between Format 2 and Format 3 by giving each parser its own local variable.

**Commit:** `refactor(inference): split XML fallback parser into named sub-parsers`

### §2 — Add reasoning-length guardrail (action-forcing short-circuit)

In `orchestrator/execution.py`, after receiving a response with `reasoning_content` but no `tool_calls` or `content`:

```python
if chat_response.reasoning_content and len(chat_response.reasoning_content) > 1500:
    if not chat_response.tool_calls and not chat_response.content:
        # Model is reasoning but not acting — force action
        await ctx.respond_callback(
            "🛑 You have been reasoning for a while but haven't emitted a tool call. "
            "Please make a tool call now."
        )
        # Optionally: inject a system message forcing tool use
```

Threshold: 1500 characters of reasoning with no actionable output triggers the guardrail.

**Commit:** `feat(orchestrator): add reasoning-length action-forcing guardrail`

### §3 — Verify MemoryStore.list_memories filtering

Check `src/hestia/persistence/memory_store.py` (or wherever `list_memories` is implemented):

1. Confirm the method accepts `platform` and `platform_user` parameters.
2. Confirm the SQL query filters by these fields.
3. If not, add the filter:

```python
query += " AND platform = ? AND platform_user = ?"
params.extend([platform, platform_user])
```

**Commit:** `fix(memory): verify list_memories filters by platform and platform_user`

### §4 — Verify context_length matches llama-server config

Compare `config.runtime.py`'s `context_length` value with the actual llama-server startup flags in `hestia-llama.service`:

- Config says 32768
- Service starts with `-c 65536`

These should match. Decide which value is correct (likely 65536 for the model's total capacity, with 32768 per slot) and document the relationship.

**Commit:** `docs(config): clarify context_length vs llama-server -c flag relationship`

### §5 — Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- `_extract_tool_calls_from_text` delegates to three named parsers
- No variable reuse between parser formats
- Reasoning guardrail triggers when >1500 chars of reasoning with no tool calls
- `list_memories` filters by platform and platform_user (with test)
- context_length documentation is accurate
- All quality gates pass

## Handoff

- Write `docs/handoffs/L167-reasoning-guardrails-and-parser-cleanup-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
