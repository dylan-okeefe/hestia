# L100 — Orchestrator Streaming Callback Plumbing

**Status:** Spec only
**Branch:** `feature/l100-orchestrator-streaming` (from `develop`)
**Depends on:** L99 (streaming inference)

## Intent

L99 added `chat_stream()` to the inference client. This loop wires it into the orchestrator execution loop so that content deltas flow from inference through to platform adapters. The orchestrator needs to:

1. Decide whether to use `chat()` or `chat_stream()` based on config
2. Accumulate streaming deltas into a complete response (for history, tool call parsing, etc.)
3. Yield partial content to platform adapters through a new streaming callback

The non-streaming path must remain the default and be completely unchanged.

## Scope

### §1 — Add StreamCallback type

In `src/hestia/orchestrator/types.py`, add alongside the existing `ResponseCallback`:

```python
StreamCallback = Callable[[str], Awaitable[None]]  # receives content deltas
```

Add `stream_callback` to `TurnContext`:

```python
stream_callback: StreamCallback | None = None
```

When `stream_callback` is `None`, the orchestrator uses the existing non-streaming path. When set, it calls `chat_stream()` and pipes deltas through.

**Commit:** `feat(orchestrator): add StreamCallback type and TurnContext field`

### §2 — Add streaming branch to inference loop

In `src/hestia/orchestrator/execution.py`, find the method that calls `self._inference.chat()` (likely in `_run_inference_loop` or similar).

Add a conditional branch:

```python
if ctx.stream_callback is not None and self._config.inference.stream:
    # Streaming path
    accumulated_content = []
    tool_calls = []
    async for delta in self._inference.chat_stream(messages, tools, reasoning_budget):
        if delta.content:
            accumulated_content.append(delta.content)
            await ctx.stream_callback(delta.content)
        if delta.tool_call_chunk:
            tool_calls.append(delta.tool_call_chunk)
        if delta.finish_reason:
            # Stream complete — build the response as if chat() returned it
            ...
    # Construct the equivalent of a chat() response from accumulated data
    # Continue with existing tool-call handling
else:
    # Existing non-streaming path (unchanged)
    response = await self._inference.chat(messages, tools, reasoning_budget)
```

**Critical details:**
- The accumulated content must be joined into a single string and used for all downstream processing (history append, tool call parsing, response callback) exactly as the non-streaming path does.
- Tool calls in streaming mode arrive as chunks that must be accumulated into complete tool call objects. llama-server sends tool calls after all content tokens. Accumulate `tool_call_chunk` deltas by index and build the final tool call list.
- Token usage (`prompt_tokens`, `completion_tokens`, `reasoning_tokens`) comes on the final delta. Update `TurnContext` totals from there.
- Error handling: if `chat_stream()` raises mid-stream, the partial content has already been sent to the client. The orchestrator should still transition to FAILED, but the user will see a partial response followed by an error message.

**Do NOT refactor the existing non-streaming path.** The `else` branch should be the exact current code, untouched.

**Commit:** `feat(orchestrator): wire chat_stream into inference loop`

### §3 — Set stream_callback in platform adapters

In each platform adapter that creates a `TurnContext`, pass `stream_callback` if the adapter supports streaming. For now, set `stream_callback=None` in ALL adapters — L101 will wire the Telegram adapter specifically. This section just ensures the plumbing exists end-to-end.

Verify that the CLI adapter, Telegram adapter, and Matrix adapter all construct `TurnContext` without errors after the new field is added.

**Commit:** `refactor(platforms): pass stream_callback=None in all adapters`

### §4 — Add tests

1. Unit test: streaming path accumulates content correctly and calls `stream_callback` for each delta.
2. Unit test: streaming path handles tool calls in streaming mode (accumulated chunks produce correct tool call objects).
3. Unit test: streaming path populates token usage from final delta.
4. Unit test: when `stream_callback is None`, the non-streaming path runs (existing behavior unchanged).
5. Unit test: when `config.inference.stream is False`, the non-streaming path runs even if `stream_callback` is set.

**Commit:** `test(orchestrator): streaming inference loop tests`

## Evaluation

- **Spec check:** `StreamCallback` type exists. `TurnContext.stream_callback` field exists. The orchestrator calls `chat_stream()` when streaming is enabled and a callback is provided, `chat()` otherwise. All platform adapters pass `stream_callback=None`.
- **Intent check:** The orchestrator can now stream content deltas to platform adapters. The streaming path produces the same final state (history, tool calls, token counts) as the non-streaming path. The non-streaming path is completely unchanged — no conditional overhead when streaming is off. Platform adapters can opt in to streaming by providing a callback (L101).
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. All existing orchestrator tests pass. Since all adapters pass `stream_callback=None`, runtime behavior is identical to pre-L100.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- Non-streaming behavior is unchanged (all adapters pass `stream_callback=None`)
- Streaming tests pass with mocked inference
- `.kimi-done` includes `LOOP=L100`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
- Next: L101 (Telegram progressive delivery)
