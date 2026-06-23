# Decisions — L221 Session Concurrency

**Status:** Resolved 2026-06-15. These are the answers to the "Decisions needed before implementation" section in `docs/development-process/L221-session-concurrency.md`. Implement against these.

1. **Lock re-entrancy invariant.** Keep `asyncio.Lock` non-reentrant. Add an explicit guard that asserts a subagent's `session_id` differs from any session whose lock is currently held, and confirm (with a test) that no other path calls `process_turn` re-entrantly on the same session. Do not make the lock re-entrant.

2. **Scheduler behavior when the target session lock is held.** Try-acquire. If the session lock is held, skip the task this tick and leave `next_run_at` so the next tick retries. Never block the scheduler loop awaiting the lock.

3. **`SessionLockManager` pruning.** Prune a session's lock on archive/reset, wired into the §4 cache-invalidation path. Do not let `_locks` grow unbounded.

4. **Sequence-validator repair strategy (§7).** Drop only provably-invalid messages (orphan tool messages with no matching assistant `tool_call_id`, adjacent-assistant duplicates), and log each drop loudly. Add tests asserting valid sequences pass untouched and that a dropped message is logged.

5. **IMAP lock scope and slot-erase cost (accepted).** The adapter-wide IMAP lock serializing the entire email channel is accepted, as is erasing the live slot on every non-DONE turn finalization. Both are correct-over-fast and acceptable.
