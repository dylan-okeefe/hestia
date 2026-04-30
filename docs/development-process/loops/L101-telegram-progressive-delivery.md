# L101 — Telegram Progressive Delivery

**Status:** Spec only
**Branch:** `feature/l101-telegram-progressive-delivery` (from `develop`)
**Depends on:** L99 (streaming inference), L100 (orchestrator streaming plumbing)

## Intent

With L99 and L100 in place, the inference client can stream and the orchestrator can pipe deltas to platform adapters. This loop wires the Telegram adapter to display progressive output: send the first chunk as a new message, then edit-in-place as more content arrives, rate-limited to avoid Telegram API throttling.

The Telegram adapter already has `edit_message` with rate limiting (1.5s between edits) and the `_md_to_tg_html` conversion. The infrastructure is in place — this loop connects it to the streaming callback.

## Scope

### §1 — Implement the streaming callback in TelegramAdapter

In `src/hestia/platforms/telegram_adapter.py`, add a method that produces a `StreamCallback` for a given chat:

```python
def _make_stream_callback(self, chat_id: int) -> StreamCallback:
    """Create a streaming callback that progressively updates a Telegram message.
    
    - First delta: send a new message (via send_message)
    - Subsequent deltas: accumulate content, edit the message (rate-limited)
    - The rate limiter prevents exceeding Telegram's edit API limits
    """
    accumulated: list[str] = []
    message_id: int | None = None
    last_edit = 0.0
    edit_interval = 1.5  # seconds — match existing rate limiter

    async def callback(delta: str) -> None:
        nonlocal message_id, last_edit
        accumulated.append(delta)
        full_text = "".join(accumulated)
        
        now = time.monotonic()
        if message_id is None:
            # First chunk — send a new message
            msg = await self.send_message(chat_id, full_text)
            message_id = msg.message_id
            last_edit = now
        elif now - last_edit >= edit_interval:
            # Rate-limited edit
            await self.edit_message(chat_id, message_id, full_text)
            last_edit = now
        # else: skip edit (too soon) — next delta will catch up

    return callback
```

**Important details:**
- The final content is still delivered via the existing `respond_callback` path. The streaming callback is purely for progressive display. When the response is complete, the orchestrator calls `respond_callback` with the full text, which should do a final `edit_message` to ensure the complete response is displayed (in case the last streaming edit was rate-limited and missed trailing content).
- Handle the case where the first chunk is very small (e.g., a single character). Consider buffering until at least N characters or M milliseconds have elapsed before sending the first message, to avoid a flash of near-empty content.
- `_md_to_tg_html` should be applied to partial content for each edit. This means incomplete markdown (e.g., an unclosed `**bold`) might render oddly during streaming. This is acceptable — the final edit will have correct formatting.

**Commit:** `feat(telegram): progressive message delivery via streaming callback`

### §2 — Wire the callback into TurnContext creation

Find where the Telegram adapter creates `TurnContext` for incoming messages. Pass `stream_callback=self._make_stream_callback(chat_id)` instead of `None`.

Also update `respond_callback` to do a final `edit_message` if streaming was active (to ensure the complete response is displayed with correct formatting):

```python
async def respond(content: str) -> None:
    if streaming_message_id is not None:
        # Final edit with complete, properly-formatted content
        await self.edit_message(chat_id, streaming_message_id, content)
    else:
        await self.send_message(chat_id, content)
```

This means the non-streaming path (send one complete message) is unchanged, and the streaming path ends with a clean final edit.

**Commit:** `feat(telegram): wire stream_callback into TurnContext creation`

### §3 — Add a first-chunk buffer

Add a small buffer before sending the first message. Accumulate deltas until either:
- At least 20 characters have been received, OR
- 500ms have elapsed since the first delta

This prevents sending a message that says "H" or "The" — the user sees a meaningful first chunk like "Here's what I found:" instead.

Implement as a simple `asyncio.sleep` check or a timer in the callback closure.

**Commit:** `feat(telegram): buffer first streaming chunk for readability`

### §4 — Add tests

1. Unit test: `_make_stream_callback` sends a new message on first delta, edits on subsequent deltas.
2. Unit test: rate limiting is respected — rapid deltas don't produce rapid edits.
3. Unit test: final `respond_callback` does an edit (not a new send) when streaming was active.
4. Unit test: first-chunk buffer works — message is not sent until threshold is met.

Mock the Telegram API calls (`send_message`, `edit_message`).

**Commit:** `test(telegram): progressive delivery tests`

## Evaluation

- **Spec check:** The Telegram adapter creates a streaming callback that sends a message on first chunk and edits on subsequent chunks, rate-limited. The final response is a clean edit with proper formatting. First-chunk buffering prevents tiny initial messages.
- **Intent check:** A Telegram user sees progressive output within ~500ms of the model starting to generate, instead of waiting 10-30 seconds for the complete response. The rate limiting prevents Telegram API throttling. The final message is identical to what would be sent without streaming — formatting is correct, content is complete.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. When `config.inference.stream` is `False` (the default), behavior is identical to pre-L99/L100/L101 — no streaming callback is created, `respond_callback` sends a single complete message.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- Streaming is gated behind `config.inference.stream = true` — default off
- Non-streaming behavior is identical to before L99
- `.kimi-done` includes `LOOP=L101`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
