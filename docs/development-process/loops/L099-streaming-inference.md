# L99 — Streaming Inference (`chat_stream`)

**Status:** Spec only
**Branch:** `feature/l99-streaming-inference` (from `develop`)

## Intent

Hestia does not stream responses. The `InferenceClient.chat()` method sends a single POST to `/v1/chat/completions` and waits for the complete response. For long responses (multi-paragraph answers, code generation), the user stares at a blank screen for 10-30 seconds before seeing anything. Streaming delivers the first token in ~200ms and shows progressive output, dramatically improving perceived responsiveness.

This loop adds the streaming capability to the inference layer ONLY. It does not wire streaming to the orchestrator or platform adapters — those are L100 and L101. The non-streaming path must remain fully functional and is the default.

## Scope

### §1 — Add `chat_stream` method to InferenceClient

In `src/hestia/core/inference.py`, add an async generator method alongside the existing `chat()`:

```python
async def chat_stream(
    self,
    messages: list[Message],
    tools: list[ToolSchema] | None = None,
    reasoning_budget: int | None = None,
) -> AsyncGenerator[StreamDelta, None]:
    """Stream a chat completion, yielding content deltas.
    
    Yields StreamDelta objects as they arrive from the server.
    The caller is responsible for accumulating the full response.
    
    Tool calls are NOT supported in streaming mode — if the model
    returns a tool_call, it will be yielded as a single delta after
    the stream completes (llama-server sends tool calls at the end).
    """
```

Implementation details:

1. Build the request payload exactly like `chat()` does, but add `"stream": true`.
2. Use `httpx` streaming: `async with self._client.stream("POST", url, json=payload) as response:`
3. Parse SSE events from the response. Each event has `data: {...}` with a `choices[0].delta` object containing either `content` (text delta) or `tool_calls` (tool call accumulation).
4. Yield `StreamDelta` objects for each content chunk.
5. Handle the `[DONE]` sentinel that signals end of stream.
6. Apply the same error translation as `_request()` — timeout → `InferenceTimeoutError`, 5xx → `InferenceServerError`, etc.

**Commit:** `feat(inference): add chat_stream async generator for SSE streaming`

### §2 — Define StreamDelta type

In `src/hestia/core/types.py` (or wherever `Message` is defined), add:

```python
@dataclass
class StreamDelta:
    """A single chunk from a streaming completion."""
    content: str | None = None  # text content delta
    tool_call_chunk: dict | None = None  # partial tool call (accumulated by caller)
    finish_reason: str | None = None  # "stop", "tool_calls", etc.
    prompt_tokens: int | None = None  # only on final chunk (usage)
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
```

Keep it simple. The orchestrator (L100) will handle accumulation logic.

**Commit:** `feat(types): add StreamDelta dataclass for streaming responses`

### §3 — Add a config flag

In `src/hestia/config.py`, add to `InferenceConfig`:

```python
stream: bool = False  # Enable streaming inference (requires llama-server SSE support)
```

Default `False` — streaming is opt-in. The orchestrator will check this flag to decide whether to call `chat()` or `chat_stream()`.

**Commit:** `feat(config): add inference.stream config flag`

### §4 — Add tests

1. Unit test `chat_stream` with a mocked SSE response — verify deltas are yielded correctly.
2. Unit test that `chat_stream` handles error responses (timeout, 5xx) with the correct exception types.
3. Unit test that `StreamDelta` is correctly constructed from various SSE payloads.

Mock the httpx streaming interface rather than hitting a real server. The SSE format from llama-server is:
```
data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}

data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5}}

data: [DONE]
```

**Commit:** `test(inference): streaming chat tests with mocked SSE`

## Evaluation

- **Spec check:** `InferenceClient.chat_stream()` exists as an async generator. `StreamDelta` type is defined. `InferenceConfig.stream` flag exists and defaults to `False`.
- **Intent check:** The streaming infrastructure is in place at the inference layer. `chat_stream` yields deltas as they arrive, doesn't buffer the full response, and handles errors the same way `chat()` does. The non-streaming `chat()` path is completely unchanged — no behavior differences when `stream=False`.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. All existing inference tests still pass. `chat()` behavior is identical.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `chat()` still works exactly as before
- `chat_stream()` yields `StreamDelta` objects from mocked SSE
- `.kimi-done` includes `LOOP=L99`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
- Next: L100 (orchestrator streaming callback plumbing)
