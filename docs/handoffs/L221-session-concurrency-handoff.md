# L221 — Per-session concurrency model handoff

**Branch:** `feature/l221-session-concurrency`  
**Parent:** `feature/l220-persistence-store-split`  
**Status:** Implementation complete, acceptance green.

## What changed

Implemented the per-session concurrency model spec from `docs/development-process/L221-session-concurrency.md`.

### §1 — `SessionLockManager`
- Added `src/hestia/orchestrator/lock.py` with a per-`session_id` `asyncio.Lock` factory.
- `Orchestrator` now owns a `SessionLockManager` and holds the session lock across the entire `process_turn` lifetime, including finalization.
- Lock entries are pruned via `release_unused` after the turn completes.
- Added `tests/unit/orchestrator/test_concurrency.py` covering same-session serialization, different-session parallelism, release-on-exception, and pruning.

### §2 — Email adapter IMAP lock
- Added an `asyncio.Lock` to `src/hestia/email/adapter.py`.
- All IMAP operations (`list_messages`, `read_message`, `search_messages`, `create_draft`, `send_draft`, `move_message`, `flag_message`) now acquire the adapter lock for the duration of the command.
- Added `tests/unit/email/test_adapter_concurrency.py`.

### §3 — Slot erase on non-DONE finalization
- Added `SlotManager.erase(session)` in `src/hestia/inference/slot_manager.py` to discard a live slot without saving KV cache.
- `TurnFinalization.finalize_turn` calls `erase` when `turn.state != TurnState.DONE` and the session has a live slot; DONE turns still call `save`.
- Added `tests/unit/inference/test_slot_finalization.py`.

### §4 — In-memory session cache invalidation
- Wrapped the `user_sessions` cache in `src/hestia/platforms/runners.py` inside a `PlatformRunner` helper with `invalidate_session_cache(platform_user)`.
- Cache is dropped on archive/reset and when a cached session is loaded in `ARCHIVED` state.
- Added `/reset` parity to `src/hestia/platforms/matrix_adapter.py` (archive session + callback), matching Telegram.
- Added `tests/unit/platforms/test_session_cache.py`.

### §5 — Degenerate tool-call turn
- Added a guardrail in `src/hestia/orchestrator/execution.py` for `finish_reason == "tool_calls"` with an empty `tool_calls` list.
- No assistant message is persisted; a retry counter on `TurnContext` is incremented; after 3 retries the turn fails with `PolicyFailureError`.
- Added `tests/unit/orchestrator/test_degenerate_tool_call.py`.

### §6 — Persist `correction=True`
- Added `correction` boolean column to `messages` schema (`src/hestia/persistence/schema.py`) with a runtime migration in `src/hestia/persistence/migrations/__init__.py`.
- Updated `MessageDTO`, mappers, and `MessageStore.append_message`/`_row_to_message` to round-trip the flag.
- Updated `src/hestia/orchestrator/quality.py` `_is_read_only_streak` to exclude `correction=True` messages.
- Updated/added `tests/unit/persistence/test_message_dto_roundtrip.py` and `tests/unit/orchestrator/test_quality_monitor.py`.

### §7 — Message sequence validator
- Added `src/hestia/context/sequence_validator.py` that repairs invalid chat-template sequences:
  - Drops adjacent `assistant` messages.
  - Drops orphan `tool` messages with no matching assistant `tool_call_id`.
- Wired it into `ContextBuilder.build` before returning messages.
- Added `tests/unit/context/test_sequence_validator.py`.

## Acceptance

```bash
uv run pytest tests/unit/ tests/integration/ -q
# 1889 passed, 6 skipped

uv run mypy src/hestia
# Success: no issues found in 198 source files

uv run ruff check src/ tests/
# 68 errors (down from 79 baseline; all remaining are pre-existing)
```

## Known issues / notes

- `tests/smoke/` includes an environment-dependent test (`test_proto_orchestrator_uses_terminal_tool`) that requires a live inference server at `localhost:8001`; it was not part of the acceptance gate.
- The branch should not merge to `develop` until L220 merges and the `error_resolutions` bootstrap fix lands (per spec).
- Next loop per roadmap is L222 (trust boundary).
