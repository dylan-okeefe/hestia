# ADR-030: Subagent delegation uses same-process, different-slot architecture

- **Status:** Accepted
- **Date:** 2026-04-10
- **Context:** Complex tasks may require extensive tool chaining that bloats the
  parent context. We need a way to offload work to subagents while keeping the
  parent context bounded. Options include: separate processes (multiprocessing),
  separate threads, or same-process with different slots.

- **Decision:**
  1. Subagents run in the **same process** as the parent orchestrator but with
     a **different session and slot** (per ADR-0005). This avoids IPC complexity
     while still providing isolation via separate KV-cache slots.
  2. The `delegate_task` tool spawns a subagent by:
     - Creating a new session via SessionStore
     - Running a separate turn via the same Orchestrator
     - Archiving the subagent session when done
  3. Results are returned via a `SubagentResult` envelope that caps parent
     context growth at ~300 tokens regardless of subagent work volume.
  4. State machine supports `AWAITING_SUBAGENT` for tracking delegation status.
  5. Timeout is enforced via asyncio.wait_for(); subagents that timeout are
     terminated and return a timeout status.

- **Consequences:**
  - A crashing subagent could crash the parent (same process). This is acceptable
    for a personal assistant where the user is present and can restart.
  - No IPC overhead, no serialization complexity.
  - Subagents benefit from SlotManager's save/restore for KV-cache persistence.
  - The parent can only have one active subagent at a time per session (can be
    relaxed later with task IDs if needed).
  - Subagent transcripts are stored as regular session history, not artifacts
    (this may change in future if storage becomes an issue).
