# ADR-013: SlotManager owns KV-cache slot lifecycle with LRU eviction

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** llama.cpp's server exposes a fixed pool of KV-cache slots
  (configured at startup via `-np N`). Slots dramatically reduce prompt
  processing time for continuation turns because the model reuses the
  cached state instead of re-ingesting the full conversation. But the
  pool is small — on our RTX 3060 we plan to run with 4 slots — and
  multiple sessions can outnumber available slots, so something has to
  decide which sessions get live slots at any moment.

  Without a dedicated manager, each adapter would grow its own ad-hoc
  slot handling, which would quickly diverge and leave stale state in
  the database.

- **Decision:**
  1. Introduce `SlotManager` as a new policy layer on top of
     `InferenceClient`. It owns the slot-id-to-session-id assignment
     map, the on-disk directory for saved slot state, and the pool size.
  2. Sessions have a temperature: `COLD` (no slot, no disk state),
     `WARM` (disk-backed, can be restored), `HOT` (live slot assigned).
     The manager transitions sessions through these states via the
     `SessionStore` as the single source of truth.
  3. `acquire(session)` guarantees the session has a live slot at turn
     start, restoring from disk if WARM, allocating fresh if COLD, or
     reusing the existing slot if HOT. If the pool is full, the
     least-recently-used session is evicted (save to disk + erase slot +
     demote to WARM) and its slot is reassigned.
  4. `save(session)` checkpoints slot state to disk after each successful
     turn without demoting temperature. The slot stays HOT; the disk
     file is a backup for eventual eviction or server restart.
  5. All SlotManager operations are serialized by a single asyncio Lock.
     Per-turn work inside the orchestrator runs outside the lock.

- **Consequences:**
  - Session resumption is fast: a WARM session's next turn skips the
    prompt re-ingestion entirely because llama.cpp restores the KV cache
    from disk.
  - The pool size is a hard tuning knob — too small and sessions thrash,
    too big and GPU memory runs out. We start at 4 for the 3060 build
    and plan to expose it as a CLI option.
  - Eviction is LRU by `last_active_at`. More sophisticated policies
    (priority, user-pinning) can replace `_pick_lru_victim` without
    changing the public API.
  - If the inference server restarts, all in-memory slot assignments
    vanish but disk state survives. The manager detects the mismatch
    via the `_assignments` map check in `acquire()` and transparently
    reallocates + restores. This is best-effort — if the restart
    happens mid-turn, that turn will fail and the user will have to
    retry.
  - Save failures during eviction propagate as hard errors rather than
    silently leaking state. The alternative (swallowing and continuing)
    would leave the database believing a session is WARM with a saved
    path that doesn't exist on disk.
