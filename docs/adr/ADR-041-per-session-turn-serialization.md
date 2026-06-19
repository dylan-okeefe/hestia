# ADR-041: Per-session turn serialization and slot/sequence safety

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** Nothing serialized turns per session. User messages, scheduler
  ticks, and nested delegation could all run `process_turn` against the same
  session at once, mutating the same DB rows, the same llama.cpp slot KV cache,
  and the same `TurnContext`. Failed turns also left stale slot state, and the
  context window could emit chat-template-invalid message sequences (L221).

- **Decision:**
  1. `SessionLockManager` (`orchestrator/lock.py`) holds one non-reentrant
     `asyncio.Lock` per `session_id`, acquired at `process_turn` entry and held
     through finalization. Locks are pruned on archive/reset.
  2. Re-entrancy guard: `process_turn` raises `RuntimeError` if it is entered for
     a session whose turn is already in progress (`current_session_id` already
     equals `session.id`). Subagents use distinct session ids, so they do not
     trip it; this catches a true re-entrant call instead of deadlocking.
  3. The scheduler try-acquires: if a task's target session lock is held
     (`lock_manager.is_locked`), it skips that task this tick and leaves
     `next_run_at` for retry, rather than blocking the tick loop.
  4. On non-DONE turn finalization the live slot is erased (not saved), so the
     next turn rebuilds context COLD from persisted messages instead of reusing
     a divergent HOT slot.
  5. A sequence validator (`context/sequence_validator.py`) drops only
     provably-invalid messages (adjacent assistants, orphan tool results) and
     logs each drop.
  6. A `correction` column on `messages` (added here, per ADR-040's deferral)
     marks injected corrections so they are excluded from read-only-streak logic.

- **Consequences:** Turns on a session are serialized; a busy session can no
  longer corrupt state or stall the scheduler. The IMAP connection is also
  serialized with an adapter lock.

- **Related:** ADR-012, ADR-013, ADR-027; `orchestrator/lock.py`,
  `orchestrator/finalization.py`, `scheduler/engine.py`,
  `context/sequence_validator.py`.
