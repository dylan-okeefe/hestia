# L161 — Direct Tool Exposure (Replace call_tool Meta-Tool)

**Status:** Spec only
**Branch:** `feature/l161-direct-tool-exposure` (from `feature/workflow-builder`)
**Depends on:** None (can land independently, but high impact)

## Intent

The current meta-tool architecture exposes only `list_tools`, `describe_tool`, and `call_tool` to the model. The model must wrap every actual tool call inside `call_tool(name=..., arguments=...)`. The 9B Qwen model struggles with this nested JSON format, repeatedly generating malformed `call_tool` arguments (empty `{}`, missing `name` field, unescaped nested JSON). This causes infinite loops, empty assistant responses, and user frustration. This loop exposes all registered tool schemas directly to the model so it can call `write_file`, `browser_get`, etc. natively.

## Review carry-forward

- *(none)*

## Scope

### §1 — Add direct tool schema generation to registry

Modify `src/hestia/tools/registry.py` `ToolRegistry`:

1. Add `direct_tool_schemas()` method that returns a `ToolSchema` for every registered tool (not just meta-tools).
2. Keep `meta_tool_schemas()` for backward compatibility (can be used in low-token-budget modes later).

```python
def direct_tool_schemas(self) -> list[ToolSchema]:
    """Return all registered tools as schemas for direct model exposure."""
    schemas: list[ToolSchema] = []
    for name, meta in self._tools.items():
        schema = ToolSchema(
            type="function",
            function=FunctionSchema(
                name=meta.name,
                description=meta.public_description,
                parameters=meta.parameters_schema or {"type": "object", "properties": {}},
            ),
        )
        schemas.append(schema)
    return schemas
```

**Commit:** `feat(tools): direct_tool_schemas() exposes all registered tools to model`

### §2 — Switch assembly to use direct schemas

Modify `src/hestia/orchestrator/assembly.py`:

1. Change `ctx.tools = self._tools.meta_tool_schemas()` to `ctx.tools = self._tools.direct_tool_schemas()`.
2. This makes the model see `write_file`, `browser_get`, `search_web`, etc. directly.

**Commit:** `feat(orchestrator): expose direct tool schemas to model`

### §3 — Update execution to handle direct tool calls

Modify `src/hestia/orchestrator/execution.py` `_dispatch_tool_call()`:

1. Remove the meta-tool dispatch path for `call_tool`.
2. All tool calls now go directly to `self._tools.describe()` / `self._tools.call()`.
3. Keep `list_tools` and `describe_tool` as regular registered tools (they're still useful for the model to discover capabilities).

```python
# Remove this block:
# handler = self._meta_tools.get(tc.name)
# if handler is not None:
#     return await handler(session, tc, allowed_tools)
```

**Commit:** `feat(orchestrator): route all tool calls directly, remove call_tool dispatch`

### §4 — Update system prompt guidance

Modify `src/hestia/config.py` default system prompt (or `config.runtime.py`):

Add a line:
```
When you need to use a tool, call it directly by name (e.g. write_file, browser_get). Do not use call_tool.
```

**Commit:** `feat(config): update system prompt for direct tool calling`

### §5 — Tests

In `tests/unit/tools/test_registry.py`:
1. Test `direct_tool_schemas()` returns schemas for all registered tools.
2. Test schema names match registered tool names.
3. Test schema descriptions match tool public descriptions.

In `tests/unit/orchestrator/test_execution.py`:
1. Test that a direct `write_file` tool call is dispatched correctly.
2. Test that `call_tool` is no longer in the dispatch table.
3. Test that malformed tool calls still return `ToolCallResult.error()` gracefully.

Run quality gates.

**Commit:** `test(tools): direct tool schema generation and dispatch coverage`

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `ruff check src/` remains at baseline or better
- Model receives ~36 tool schemas directly instead of 3 meta-tools
- Calling `write_file` directly works without `call_tool` nesting

## Risks & Mitigations

- **Token cost increase:** 36 tool schemas ≈ 3000–4000 tokens vs. 80 tokens for meta-tools. Mitigation: context window is 16K, and the compression system handles this. Monitor actual token counts.
- **Model overwhelmed by choice:** May cause the model to call wrong tools. Mitigation: clear system prompt guidance + tool descriptions are already descriptive.

## Handoff

- Write `docs/handoffs/L161-direct-tool-exposure-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
