# L213 — Concurrency & Replay Protection Handoff

## What was done

### §1 — H3: SlotManager double-eviction race

**File:** `src/hestia/inference/slot_manager.py`

- `_evict_session_locked` now removes the victim from `_assignments` **before** releasing `self._lock` for slow HTTP I/O. This prevents `_pick_lru_victim` from selecting the same victim twice.
- I/O exceptions are caught, logged, and swallowed instead of re-raised. The victim is already excluded from the pool, so continuing is safe.
- A `released` flag tracks whether the coroutine actually released the lock; the `finally` block unconditionally re-acquires it so callers always exit with the lock held.
- `_allocate_slot` handles the case where the freed slot was stolen by another coroutine during the I/O window: if `victim_slot_id` is already back in `_assignments`, it recurses to find another slot.

**Test:** `tests/unit/test_slot_manager.py::test_concurrent_acquire_no_double_eviction`
- Creates a `pool_size=1` manager with a slow `slot_save`.
- Starts two concurrent `acquire()` calls when the pool is full.
- Asserts the LRU victim is saved exactly once (no double-eviction) and no exception / `KeyError` occurs.

### §2 — H4: Webhook replay protection

**File:** `src/hestia/web/routes/webhooks.py`

- Added a module-level `OrderedDict[str, None]` (`_seen_signatures`) acting as a bounded LRU cache (max 1000 entries).
- After signature verification, the route checks the cache.
  - Seen → `HTTPException(status_code=409, detail="Duplicate webhook signature")`
  - New → insert into cache and proceed.

**Test:** `tests/unit/workflows/test_webhook_auth.py::test_replay_attack_same_signature_twice`
- Updated to assert the first identical request returns `202` and the second returns `409`.

**Infrastructure:** `tests/conftest.py`
- Added autouse fixture `_clear_webhook_seen_cache` so the module-level cache is reset before every test, preventing cross-test contamination.

## Quality gates

| Gate | Result | Notes |
|------|--------|-------|
| `uv run pytest tests/unit/ tests/integration/ -q` | ✅ 1691 passed, 6 skipped | |
| `uv run mypy src/hestia` | ✅ Success (no issues in 194 files) | Required clearing `.mypy_cache` first due to a mypy 1.20.0 internal error triggered by stale cache. |
| `uv run ruff check src/ tests/` | ⚠️ Pre-existing failures | Failures exist on `origin/develop` and are **not caused by these changes**. Ruff on the files touched by this handoff is clean except for one pre-existing `E501` at `slot_manager.py:150`. |

## Commits

1. `fix(slot_manager): prevent double-eviction race by removing victim before I/O`
2. `fix(webhooks): add replay protection via bounded LRU signature cache`
3. `test: cover slot-manager race and webhook replay protection`

## Files changed

- `src/hestia/inference/slot_manager.py`
- `src/hestia/web/routes/webhooks.py`
- `tests/unit/test_slot_manager.py`
- `tests/unit/workflows/test_webhook_auth.py`
- `tests/conftest.py`
