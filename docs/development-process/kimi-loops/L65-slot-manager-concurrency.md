# L65 — SlotManager Concurrency & Correctness

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l65-slot-manager-concurrency` (from `develop`)

## Goal

Fix three correctness and performance issues in `SlotManager` that compound under load: N+1 DB queries during eviction, holding an asyncio lock across slow HTTP I/O, and silently swallowing slot-save failures.

---

## Intent & Meaning

`SlotManager` is a concurrency-critical component. Every turn that needs a KV-cache slot calls `acquire()`, which may need to evict a cold session. The evaluation found that eviction:

1. **Queries the DB N times sequentially** (`_pick_lru_victim`) — with `pool_size=4`, every eviction is 4 round-trips.
2. **Holds the async lock across HTTP calls** (`_evict_session_locked`) — if llama-server is slow, every other `acquire()` stalls.
3. **Ignores HTTP 400 on save** — the session is marked WARM but no snapshot was written; next resume silently rebuilds from cold.

The intent is not just "make it faster." It is **make it honest under concurrency**. A slow llama-server should not stall the entire orchestrator. A failed save should not lie about session temperature. These are daemon-grade robustness issues — the difference between "works on my laptop" and "runs for a month on a server."

---

## Scope

### §1 — Batch query in `_pick_lru_victim`

**File:** `src/hestia/inference/slot_manager.py`
**Evaluation:** `for sid in candidates: s = await self._store.get_session(sid)` — N serial DB queries.

**Change:**
Replace the loop with a single `WHERE id IN (...)` query. Add a `get_sessions_batch(ids: list[str])` method to `SessionStore` (or use the existing `list` method with a filter) if needed.

```python
# Before
for sid in candidates:
    s = await self._store.get_session(sid)
    if s and s.slot_id is not None:
        return sid

# After
sessions = await self._store.get_sessions_batch(candidates)
for s in sessions:
    if s.slot_id is not None:
        return s.id
```

**Intent:** One query, one round-trip, one lock hold duration. The lock is the bottleneck; minimizing work inside it is the priority.

**Commit:** `perf(slot_manager): batch LRU victim query to single DB round-trip`

---

### §2 — Release lock before HTTP I/O in `_evict_session_locked`

**File:** `src/hestia/inference/slot_manager.py`
**Evaluation:** `slot_save` and `slot_erase` are HTTP calls to llama-server. The lock is held for the entire duration.

**Change:**
Restructure `_evict_session_locked` into two phases:
1. **Under lock:** determine `slot_id`, remove from `_assignments`, set session state.
2. **Outside lock:** call `self._inference.slot_erase(slot_id)`.

If the erase fails, log the error but the assignment state is already consistent — the slot is free from Hestia's perspective even if llama-server disagrees. On next acquire, a fresh slot will be allocated.

**Intent:** The lock protects the `_assignments` dict, not the universe. HTTP I/O has no business inside a critical section that blocks every turn.

**Commit:** `fix(slot_manager): release lock before HTTP I/O during eviction`

---

### §3 — Fail loudly on slot-save HTTP 400

**File:** `src/hestia/inference/slot_manager.py`
**Evaluation:** If `slot_save` returns HTTP 400 (mismatched `slot_dir`), the error is logged but the session continues as if save succeeded. Next resume fails silently and falls back to cold rebuild.

**Change:**
- In `acquire()` or `_save_session_slot()`, if `slot_save` raises `InferenceServerError` with 400 status, propagate it as a `SlotSaveError` (or log at `ERROR` level and mark the session `COLD`, not `WARM`).
- Do not mark a session `WARM` unless the HTTP response confirms success.

**Intent:** Silent degradation is worse than a loud failure. If warm resume is broken, the operator should know immediately from logs, not discover it via mysteriously slow restarts.

**Commit:** `fix(slot_manager): do not mark session WARM when slot_save fails`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `_pick_lru_victim` issues at most one DB query.
- `_evict_session_locked` releases the lock before `slot_erase`.
- Failed `slot_save` does not mark the session `WARM`.

## Acceptance (Intent-Based)

- **Eviction under load does not stall turns.** Verify by timing `acquire()` under synthetic load (mock slow `slot_erase` — concurrent `acquire()` calls should not block on each other).
- **A broken slot_dir configuration is discoverable.** Verify by simulating a 400 response — the log should contain an ERROR, and the session temperature should remain COLD.
- **The code makes the lock scope visually obvious.** A reader should see `async with self._lock:` around a small block of dict mutation, not wrapped around 20 lines of logic.

## Handoff

- Write `docs/handoffs/L65-slot-manager-concurrency-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l65-slot-manager-concurrency` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
