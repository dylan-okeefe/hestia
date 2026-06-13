# Spec — Per-session concurrency model

**Status:** HOLD-FOR-REVIEW  
**Review source:** docs/reviews/develop-review-2026-06-12.md (Backend correctness / Security sections)  
**Scope:** One coherent spec for all concurrency/session-lifecycle findings. Do NOT split into independent loops.

## Problem statement

Three independent drivers can currently execute turns against the same session at the same time:

1. User messages from Telegram/Matrix.
2. Scheduler ticks firing scheduled tasks.
3. Nested delegation / subagent calls.

There is no per-session serialization. Two concurrent `process_turn` calls mutate the same DB rows, the same llama.cpp slot KV cache, and the same `TurnContext`. In addition, the email adapter reuses a single IMAP connection across concurrent tasks, and failed turns leave stale slot state.

## Findings this spec covers

- No per-session turn serialization (`orchestrator/engine.py process_turn`, `platforms/runners.py on_message`, `scheduler/engine.py _fire_task`).
- Shared IMAP connection unsafe under concurrent async (`email/adapter.py` ContextVar reuse; `app.py:232` shares one `EmailAdapter`).
- Failed/partial turns leave stale slot KV cache (`orchestrator/finalization.py:103`).
- Stale in-memory session cache (`runners.py:153`).
- `finish_reason="tool_calls"` with zero valid tool calls burns iterations (`execution.py:183`).
- `correction=True` flag not persisted (missing messages column).
- Context window can emit invalid message sequences (`context/history_window_selector.py`).

## Design

### 1. `SessionLockManager`

Introduce `src/hestia/orchestrator/lock.py`:

```python
class SessionLockManager:
    """Per-session_id asyncio.Lock factory."""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
        return lock

    def release_unused(self, session_id: str) -> None:
        """Optional: prune locks for archived sessions."""
        ...
```

- `Orchestrator` owns a `SessionLockManager`.
- `process_turn` acquires the lock for `session.id` at entry and holds it until finalization completes.
- `PlatformRunner.on_message` and `SchedulerEngine._fire_task` do **not** call `process_turn` directly; they schedule a turn via a single `Orchestrator.process_turn()` invocation, which internally serializes.

### 2. Email adapter concurrency

- Add an `asyncio.Lock` to `EmailAdapter` for IMAP operations.
- Email tools (`email_list`, `email_read`, `email_search`, `email_move`, `email_flag`) acquire the adapter lock for the duration of the IMAP command.
- The inbound poller and tool calls cannot interleave commands on the same IMAP socket.
- Alternatively, mark email tools with `ordering="serial"` in the tool registry and ensure the executor respects it; the adapter lock is the lower-level guarantee.

### 3. Slot lifecycle on non-DONE finalization

- In `orchestrator/finalization.py`, when `turn.state != TurnState.DONE`:
  - Erase the live slot (call slot manager erase/rebuild).
  - Do **not** save the current KV cache to disk.
- The next turn starts from persisted messages (COLD/WARM rebuild) rather than reusing a HOT slot that diverges from history.

### 4. In-memory session cache invalidation

- `PlatformRunner.user_sessions[platform_user]` cache must invalidate when:
  - A session is archived or reset.
  - A session's state changes to `ARCHIVED`.
- Add Matrix parity for `/reset` (Telegram already clears; Matrix needs equivalent).
- Consider replacing the unbounded dict with a TTL + invalidation wrapper.

### 5. Degenerate tool-call turn

- In `orchestrator/execution.py`, when `chat_response.finish_reason == "tool_calls"` but `len(chat_response.tool_calls) == 0` (all structured calls failed JSON validation):
  - Do not persist an assistant message with no tools/results.
  - Treat as a degenerate response and retry, incrementing a retry counter to prevent infinite loops.

### 6. Persist `correction=True`

- Add `correction` boolean column to the messages table via runtime migration.
- Write `correction=True` when the orchestrator injects a correction message.
- Read it back so `quality._is_read_only_streak` excludes injected corrections.

### 7. Valid chat-template message sequences

- Add a validator in `context/history_window_selector.py` (or a new `context/sequence_validator.py`):
  - No duplicate `role="assistant"` messages unless separated by `role="user"`.
  - No orphan `role="tool"` / `role="function"` messages without a preceding assistant message that contains the matching `tool_call_id`.
- Run the validator before the context is handed to the inference client; log loudly and repair by dropping invalid messages.

## Tests that must pass before merging

1. Two concurrent `process_turn` calls on the same `session_id` serialize; the second waits for the first.
2. An email-triggered workflow node and a user message cannot run slot operations simultaneously.
3. A failed turn erases the live slot; the next turn rebuilds from DB.
4. Reloaded messages preserve `correction=True`; quality streak logic is stable.
5. History window selector output passes an OpenAI-message-sequence validator.
6. Concurrent email tool calls do not interleave IMAP commands.

## Files likely to change

- New: `src/hestia/orchestrator/lock.py`, `src/hestia/context/sequence_validator.py`
- Modify: `src/hestia/orchestrator/engine.py`, `src/hestia/orchestrator/execution.py`, `src/hestia/orchestrator/finalization.py`, `src/hestia/platforms/runners.py`, `src/hestia/platforms/telegram_adapter.py`, `src/hestia/platforms/matrix_adapter.py`, `src/hestia/scheduler/engine.py`, `src/hestia/email/adapter.py`, `src/hestia/context/history_window_selector.py`, `src/hestia/persistence/schema.py`, `src/hestia/persistence/sessions.py`
- Tests: `tests/unit/orchestrator/test_concurrency.py`, `tests/unit/email/test_adapter_concurrency.py`, `tests/unit/inference/test_slot_lifecycle.py`, `tests/unit/context/test_sequence_validator.py`

## Risks & open questions

- **Deadlock.**  Holding a per-session lock across `process_turn` means any nested call (e.g., subagent) must use the same lock manager and not re-enter on the same session.
- **Scheduler backlog.**  If a scheduled task is blocked behind a long user turn, scheduler ticks will queue. Decide whether to skip late ticks or queue them.
- **IMAP lock scope.**  The adapter lock serializes all email tools; if one tool is slow, the whole email channel stalls. Acceptable for correctness, but may need per-mailbox locks later.
- **Slot erase cost.**  Rebuilding from messages on every non-DONE turn is correct but slower. Consider keeping HOT only on DONE.

## Dependency

- Must land **after** the `error_resolutions` schema bootstrap fix if the messages schema migration uses the same bootstrap path.
- Should land **before** or together with the `persistence/sessions.py` store split, because the store split will move message/turn persistence and the correction column work should be in the new `MessageStore`.
