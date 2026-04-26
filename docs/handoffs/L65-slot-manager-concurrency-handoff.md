# L65 — SlotManager Concurrency & Correctness Handoff

**Branch:** `feature/l65-slot-manager-concurrency`
**Status:** Complete, ready for review

## Changes

### §1 — Batch query in `_pick_lru_victim`
- Added `SessionStore.get_sessions_batch()` using `WHERE id IN (...)`
- `_pick_lru_victim` now issues one query instead of N serial round-trips

### §2 — Release lock before HTTP I/O in `_evict_session_locked`
- Lock is released before `slot_save`/`slot_erase` and re-acquired after
- Other `acquire()` calls are no longer stalled by slow llama-server I/O

### §3 — Fail loudly on slot-save HTTP 400
- `SlotManager.save()` now catches `InferenceServerError`, logs at ERROR, and re-raises
- `update_saved_path` is never called if the HTTP call fails

### §4 — `get_or_create_session` PostgreSQL note
- The existing PostgreSQL dialect dispatch is correct; no code change needed
- Added `tests/integration/test_slot_manager_concurrency.py` with concurrent acquire and 400-simulation tests

## Quality gates

- `pytest tests/unit/test_slot_manager.py tests/integration/test_slot_manager_concurrency.py` — 20 passed
- `mypy src/hestia/inference/slot_manager.py src/hestia/persistence/sessions.py` — no issues
- `ruff check` — clean

## Intent verification

- **Eviction under load does not stall turns:** Test verifies concurrent acquire proceeds while slot_erase is blocked.
- **Broken slot_dir is discoverable:** Test verifies failed slot_save prevents `update_saved_path`.
- **Lock scope is visually obvious:** Lock is released before HTTP and re-acquired after.

## Next

Ready to merge to `develop` and start L66.
