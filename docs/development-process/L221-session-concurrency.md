# L221 — Per-session concurrency model

**Status:** Spec ready. Decisions resolved in `docs/reviews/decisions-session-concurrency.md` (the "Decisions needed" section below is now answered there). Feature branch work; implement after L220; do not merge to develop until release-prep merge sequence.  
**Branch:** `feature/l221-session-concurrency` (from `develop` after L220 merges)  
**Spec source:** `docs/reviews/spec-session-concurrency.md`  
**Depends on:** L220 (`persistence/sessions.py` store split), `error_resolutions` schema bootstrap fix

## Goal

Serialize per-session turn execution, protect the shared IMAP connection, erase stale slot state on non-DONE turns, invalidate in-memory session caches, and persist the `correction` flag on injected messages.

## Review carry-forward

- *(none — this is a new spec-driven arc)*

## Decisions needed before implementation

1. **Lock re-entrancy invariant.** `asyncio.Lock` is non-reentrant and is held across all of `process_turn`. Subagents currently get a distinct session (`delegate_task` calls `create_session`), so they do not re-enter, but this is load-bearing and implicit. Decide: enforce it as an explicit invariant (assert a subagent's `session_id` differs from any held lock, and confirm no other path calls `process_turn` re-entrantly on the same session), or make the lock re-entrant. Recommend: keep non-reentrant and add a guard, since the design already separates subagent sessions.
2. **Scheduler behavior when the target session lock is held (currently unaddressed).** `_tick` awaits `_fire_task` then `process_turn` sequentially, so a scheduled task whose session is mid-turn will block the whole scheduler loop until the lock frees. Decide: try-acquire and skip-with-reschedule, queue, or block. Recommend: try-acquire; if the session is busy, leave `next_run_at` and move on, so one busy session cannot stall the scheduler.
3. **`SessionLockManager` pruning.** `_locks` grows per `session_id` indefinitely. Decide when `release_unused` runs (on archive/reset, a TTL sweep, or accept the leak). Recommend: prune on archive/reset, wired into the §4 cache-invalidation path.
4. **Sequence-validator repair strategy (§7).** "Drop invalid messages" silently changes what the model sees. Decide: drop the provably-invalid orphan/duplicate only, with loud logging; or pass-through-and-log in production with drop behind a flag. Recommend: drop only provably-invalid messages, log loudly, and add a test asserting a dropped message is logged.
5. **Confirm the minor calls:** the adapter-wide IMAP lock serializes the entire email channel, and slot-erase runs on every non-DONE turn. Confirm both are acceptable.

## Scope

### §1 — `SessionLockManager`

Create `src/hestia/orchestrator/lock.py`.

```python
class SessionLockManager:
    """Per-session_id asyncio.Lock factory."""

    def __init__(self) -> None:
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
        """Prune lock for archived/deleted sessions (best-effort)."""
```

**Wiring:**
- `Orchestrator` owns one `SessionLockManager` instance.
- `process_turn` acquires the lock for `session.id` at entry and holds it until finalization completes.
- `PlatformRunner.on_message` and `SchedulerEngine._fire_task` continue to call `Orchestrator.process_turn()`; the orchestrator provides the serialization.
- Subagent delegations run in different `session_id`s, so they do not re-enter the same lock.

**Tests:**
- `tests/unit/orchestrator/test_concurrency.py`:
  - Two concurrent `process_turn` calls for the same `session_id` execute sequentially.
  - Two concurrent calls for different session IDs run in parallel.
  - Lock is released after the turn finalizes even on exception.

**Commit:** `feat(orchestrator): add SessionLockManager to serialize per-session turns`

### §2 — Email adapter concurrency

Protect the shared IMAP connection in `src/hestia/email/adapter.py`.

**Implementation:**
- Add an `asyncio.Lock` to `EmailAdapter`.
- All IMAP operations (`email_list`, `email_read`, `email_search`, `email_move`, `email_flag`) acquire the adapter lock for the duration of the command.
- Alternatively, mark email tools with `ordering="serial"` as a secondary signal; the adapter lock is the required guarantee.

**Tests:**
- `tests/unit/email/test_adapter_concurrency.py`:
  - Two concurrent email tool calls do not interleave IMAP commands.
  - Lock is released after each command.

**Commit:** `fix(email): serialize IMAP operations with adapter lock`

### §3 — Slot lifecycle on non-DONE finalization

Update `src/hestia/orchestrator/finalization.py`.

**Implementation:**
- In `finalize_turn`, when `turn.state != TurnState.DONE`:
  - If the session has a live slot, erase it via `SlotManager` (do not save KV cache to disk).
- The next turn will rebuild context from persisted messages and start COLD/WARM.

**Tests:**
- `tests/unit/inference/test_slot_lifecycle.py`:
  - A failed turn erases the live slot.
  - A done turn still saves the slot.

**Commit:** `fix(orchestrator): erase live slot on non-DONE turn finalization`

### §4 — In-memory session cache invalidation

Update `src/hestia/platforms/runners.py` and adapters.

**Implementation:**
- `PlatformRunner.user_sessions[platform_user]` cache must drop the entry when:
  - A session is archived or reset.
  - A session's state changes to `ARCHIVED`.
- Add Matrix parity for `/reset` (Telegram already clears via `register_reset_callback`).
- Consider wrapping the dict in a small helper with explicit invalidation instead of scattering `pop` calls.

**Tests:**
- `tests/unit/platforms/test_session_cache.py`:
  - After `/reset`, the cached session is removed and a new session is created on next message.
  - Matrix `/reset` behaves the same as Telegram.

**Commit:** `fix(platforms): invalidate in-memory session cache on archive/reset`

### §5 — Degenerate tool-call turn

Update `src/hestia/orchestrator/execution.py`.

**Implementation:**
- When `chat_response.finish_reason == "tool_calls"` but `len(chat_response.tool_calls) == 0` (all structured calls failed JSON validation):
  - Do not persist an assistant message with no tools/results.
  - Treat as a degenerate response, increment a retry counter, and continue the loop.
  - Fail with `MaxIterationsError` or `PolicyFailureError` if the counter exceeds a reasonable cap.

**Tests:**
- `tests/unit/orchestrator/test_degenerate_tool_call.py`:
  - Empty tool-call batch does not append a message.
  - Turn retries and eventually fails.

**Commit:** `fix(orchestrator): handle finish_reason=tool_calls with zero valid tool calls`

### §6 — Persist `correction=True`

Add the `correction` column to `messages` and wire it through the split stores.

**Implementation:**
- Add `correction` boolean column to `src/hestia/persistence/schema.py` `messages` table (default `False`).
- Add a runtime migration in `src/hestia/persistence/migrations/` to add the column idempotently.
- Update `MessageDTO` in `src/hestia/persistence/dto.py` to include `correction: bool`.
- Update `src/hestia/orchestrator/mappers.py` to map `Message.correction`.
- Update `MessageStore.append_message` to persist `correction`.
- Update quality-monitor read path in `src/hestia/orchestrator/quality.py` (`_is_read_only_streak`) to exclude messages where `correction=True`.

**Tests:**
- `tests/unit/persistence/test_message_dto_roundtrip.py` (updated): correction flag round-trips.
- `tests/unit/orchestrator/test_quality_monitor.py`: injected corrections are excluded from read-only streak detection.

**Commit:** `feat(persistence): persist correction flag on messages and exclude from streak logic`

### §7 — Valid chat-template message sequences

Add a validator for message sequences handed to the inference client.

**Implementation:**
- Create `src/hestia/context/sequence_validator.py`.
- Rules:
  - No adjacent `role="assistant"` messages unless separated by `role="user"`.
  - No orphan `role="tool"` messages without a preceding assistant message that contains the matching `tool_call_id`.
- Run the validator in `ContextBuilder.build` before returning messages; log loudly and repair by dropping invalid messages.

**Tests:**
- `tests/unit/context/test_sequence_validator.py`:
  - Adjacent assistant messages are repaired.
  - Orphan tool messages are dropped.
  - Valid sequences pass untouched.

**Commit:** `feat(context): add message-sequence validator for chat-template correctness`

## Tests

- New unit tests:
  - `tests/unit/orchestrator/test_concurrency.py`
  - `tests/unit/email/test_adapter_concurrency.py`
  - `tests/unit/inference/test_slot_lifecycle.py`
  - `tests/unit/platforms/test_session_cache.py`
  - `tests/unit/orchestrator/test_degenerate_tool_call.py`
  - `tests/unit/orchestrator/test_quality_monitor.py`
  - `tests/unit/context/test_sequence_validator.py`
- Updated tests: any test that constructs `Message`/`MessageDTO` without the new `correction` field.
- Keep existing tests green.

## Acceptance

- `uv run pytest tests/unit/ tests/integration/ -q` green
- `uv run mypy src/hestia` reports 0 errors
- `uv run ruff check src/ tests/` remains at baseline or better (project line-length is 120)
- `.kimi-done` includes `LOOP=L221`
- Manual smoke test: run two rapid messages to the same Telegram/Matrix user and confirm they serialize.

## Handoff

- Write `docs/handoffs/L221-session-concurrency-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to the trust-boundary loop (L222)

## Critical rules recap

- Do not merge or push without Dylan's okay.
- Land only after L220 and the `error_resolutions` bootstrap fix.
- The `correction` column migration lives in the split `MessageStore`.
- Holding a per-session lock across `process_turn` means no nested call may re-enter the same `session_id` lock.
