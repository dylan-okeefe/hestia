# L164 — Execution Refactor: Deduplicate Tool-Call Handling

**Status:** Spec only  
**Branch:** `feature/l164-execution-refactor` (from `feature/workflow-builder-runtime`)  
**Depends on:** L163 (repo hygiene)

## Intent

The runtime branch review identified ~70 lines of copy-pasted code in `orchestrator/execution.py` (lines 118–188 vs 196–257). Both the `finish_reason == "stop"` branch and the `finish_reason == "tool_calls"` branch contain identical logic for tool dispatch, delegation checks, context rebuild, reasoning display, and iteration tracking. This is a maintenance hazard.

## Review carry-forward

- *(none)*

## Scope

### §1 — Extract `_handle_tool_calls` method

Create a private method on the orchestrator (or a standalone helper):

```python
async def _handle_tool_calls(
    self,
    ctx: TurnContext,
    turn: Turn,
    chat_response: ChatResponse,
    transition: TransitionCallback,
    set_typing: Callable[[bool], Awaitable[None]],
) -> TurnState:
    """Dispatch tool calls, handle delegation, and advance the turn."""
    tool_names = [tc.name for tc in chat_response.tool_calls]
    ctx.tool_chain.extend(tool_names)
    logger.debug("Executing tools: %s", ", ".join(tool_names))
    await set_typing(True)

    # Show reasoning before tool status
    if chat_response.reasoning_content:
        try:
            reasoning_display = f"💭 {chat_response.reasoning_content[:2000]}"
            if len(chat_response.reasoning_content) > 2000:
                reasoning_display += "\n\n... (reasoning truncated)"
            await ctx.respond_callback(reasoning_display)
        except Exception:
            pass

    # Status update (first iteration only)
    if turn.iterations == 0:
        status = self._format_tool_status(tool_names)
        if status:
            try:
                await ctx.respond_callback(status)
            except Exception:
                pass

    # ... rest of the tool dispatch logic ...
    # Return the next state (e.g., TurnState.AWAITING_TOOL_RESULTS)
```

**Commit:** `refactor(orchestrator): extract _handle_tool_calls method`

### §2 — Replace duplicated branches with method calls

In `execution.py`, replace both the `finish_reason == "tool_calls"` branch and the `finish_reason == "stop"` branch with a single call to `self._handle_tool_calls(...)`.

Before:
```python
if finish_reason == "tool_calls":
    # 70 lines of logic
elif finish_reason == "stop" and chat_response.tool_calls:
    # identical 70 lines of logic
```

After:
```python
if finish_reason in ("tool_calls", "stop") and chat_response.tool_calls:
    return await self._handle_tool_calls(ctx, turn, chat_response, transition, set_typing)
```

**Commit:** `refactor(orchestrator): deduplicate tool-call handling branches`

### §3 — Verify no behavior change

Run the full test suite, especially:
- `tests/unit/orchestrator/test_execution.py`
- `tests/integration/test_orchestrator.py`
- `tests/unit/test_orchestrator_streaming.py`

**Commit:** *(no code change — verification only)*

### §4 — Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- `orchestrator/execution.py` has no duplicated 70-line blocks
- `_handle_tool_calls` is called from exactly one place per finish_reason branch
- All existing tests pass without modification
- `mypy` reports 0 errors in `execution.py`

## Handoff

- Write `docs/handoffs/L164-execution-refactor-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
