# L213 — Concurrency & Replay Protection

## Goal
Fix the SlotManager eviction race and add webhook replay protection.

## §1 — H3: SlotManager double-eviction race

File: `src/hestia/inference/slot_manager.py`

Problem: `_evict_session_locked` releases `self._lock` at line ~231 to perform
slow HTTP I/O (slot_save/slot_erase), then reacquires. During the release window,
another coroutine can enter `_allocate_slot`, pick the same victim, and trigger
a second eviction → concurrent slot_save, double release_slot, KeyError.

Fix options (pick the simplest that works):
1. **Mark victim as "evicting" before releasing lock.** Remove from `_assignments`
   before the I/O, so `_pick_lru_victim` can't select it. If reacquisition fails,
   the victim is already gone from the map (acceptable — slightly eager eviction).
2. **Hold lock for whole eviction.** Simpler but blocks all slot operations during
   slow HTTP I/O. Acceptable if evictions are rare.
3. **Per-slot lock + manager lock.** Most correct but more complex.

Recommendation: Option 1 — remove victim from `_assignments` and `_slots` before
releasing the lock, perform I/O, then if I/O fails, log and continue. The victim
is already excluded from future allocation. If slot_save fails, the slot is lost
from the cache but that's better than a race.

Also add a test that reproduces the race: start 2+ concurrent turns when pool is
full, assert no double-eviction / KeyError.

## §2 — H4: Webhook replay protection

File: `src/hestia/web/routes/webhooks.py`

Problem: A captured valid (timestamp, body, signature) can be replayed unlimited
times within the ±300s window. No nonce or seen-signature cache.

Fix:
- Add a bounded LRU cache of recently-seen signatures (or HMAC digests).
- When a webhook request arrives, after verifying the signature and timestamp,
  check if the signature digest is in the cache.
- If seen → reject with 409 Conflict (or 429).
- If new → add to cache and proceed.
- Cache size: ~1000 entries per endpoint (bounded to prevent memory growth).
- Use `functools.lru_cache` or a simple `collections.OrderedDict` with a max size.

Update tests:
- `tests/unit/workflows/test_webhook_auth.py`: The test at :268-301 currently
  expects two identical posts to both return 202. Update it to assert the second
  identical request is rejected.

## Quality Gates
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff
Write `docs/handoffs/L213-concurrency-replay-protection-handoff.md`.
