# Hestia Phase 2a Report — SlotManager

**Date:** 2026-04-09

## Overview

Phase 2a adds the **SlotManager**: the subsystem that maps sessions to llama.cpp server slots, saves/restores KV-cache state to disk, and evicts under pressure. This is the last core-engine piece before adding real chat platform adapters.

## Components Delivered

### 1. SessionStore Archive on Reset (v0.1.0 leftover fix)

- Added `archive_session()` method to mark sessions as ARCHIVED
- Extended `create_session()` with optional `archive_previous` parameter
- Updated CLI `/reset` to archive the previous session atomically
- `get_or_create_session()` already filtered on ACTIVE state

### 2. SessionStore Slot-Path Persistence

- Extended `assign_slot()` with `clear_saved_path: bool` parameter
- Extended `release_slot()` with `saved_path: str | None` parameter  
- Added `update_saved_path()` helper for checkpointing

### 3. SlotManager (`src/hestia/inference/slot_manager.py`)

**Public API:**
- `acquire(session) -> SlotAssignment` - Ensure session has a live slot
- `save(session)` - Checkpoint slot state to disk
- `evict_by_id(session_id)` - Forcibly evict a specific session

**Key behaviors:**
- COLD sessions get fresh slots
- WARM sessions restore from disk
- HOT sessions reuse existing slots (with assignment map verification)
- Pool-full eviction uses LRU by `last_active_at`
- All operations serialized by asyncio Lock

### 4. Orchestrator Integration

- Added optional `slot_manager: SlotManager | None` parameter
- Calls `slot_manager.acquire()` at turn start
- Calls `slot_manager.save()` after successful turns (DONE only)
- Falls back to `session.slot_id` when no SlotManager injected

### 5. CLI Wiring

- Added `--slot-dir` option (default: `./slots`)
- Added `--slot-pool-size` option (default: `4`)
- `hestia init` creates slot directory
- Both `chat` and `ask` commands pass SlotManager to Orchestrator

## Test Coverage

**142 tests passing** (+19 from Phase 1c baseline of 123):
- 4 new SessionStore archive/slot tests
- 6 SlotManager unit tests
- 1 Slot lifecycle integration test
- 8 total new test files/modules

**New test files:**
- `tests/unit/test_session_store_slot.py`
- `tests/unit/test_slot_manager.py`
- `tests/integration/test_slot_lifecycle.py`

## Architecture Decision Records

- **ADR-013**: SlotManager owns KV-cache slot lifecycle with LRU eviction

## Quality Checks

- **pytest:** 142 passed ✅
- **ruff:** Clean (pre-existing warnings in scripts/ only) ✅
- **mypy:** 9 errors, all pre-existing ✅

## Files Added/Modified

**New files:**
- `src/hestia/inference/__init__.py`
- `src/hestia/inference/slot_manager.py`
- `tests/unit/test_session_store_slot.py`
- `tests/unit/test_slot_manager.py`
- `tests/integration/test_slot_lifecycle.py`
- `docs/handoffs/HESTIA_PHASE_2A_REPORT_20260409.md`

**Modified files:**
- `src/hestia/persistence/sessions.py` - Archive and slot-path methods
- `src/hestia/cli.py` - SlotManager wiring
- `src/hestia/orchestrator/engine.py` - SlotManager integration
- `tests/unit/test_session_store_turns.py` - Archive tests
- `tests/unit/test_cli_meta_commands.py` - Updated /reset test
- `docs/DECISIONS.md` - ADR-013

## Commits (8 total)

```
614d0e1 docs(adr): add ADR-013 for SlotManager and KV-cache lifecycle strategy
a15eac7 test(integration): add end-to-end slot lifecycle test
b42c3de test(inference): add unit tests for SlotManager
7d8f03e feat(cli): wire SlotManager into chat and ask commands
ed92e44 feat(orchestrator): integrate SlotManager for per-turn slot acquisition
f971841 feat(inference): add SlotManager for KV-cache slot assignment and eviction
ee7c11d feat(persistence): extend assign_slot and release_slot with disk-path tracking
dce32ff fix(persistence): archive previous session atomically on create_session
```

## Next Steps (Phase 2b/2c)

With SlotManager complete:
- Matrix adapter (real-time messaging)
- Telegram adapter
- Scheduler (background task management)

## Blockers

**None.** Phase 2a complete. Branch is ready for:
1. Dylan review
2. Push to remote
3. Merge to develop
4. Tag v0.2.0-dev.1 (or wait for full Phase 2 completion)

---

**Git Log Verification:**

```
614d0e1 Dylan O'Keefe <dylanokeefedev@gmail.com> docs(adr): add ADR-013 for SlotManager and KV-cache lifecycle strategy
a15eac7 Dylan O'Keefe <dylanokeefedev@gmail.com> test(integration): add end-to-end slot lifecycle test
b42c3de Dylan O'Keefe <dylanokeefedev@gmail.com> test(inference): add unit tests for SlotManager
7d8f03e Dylan O'Keefe <dylanokeefedev@gmail.com> feat(cli): wire SlotManager into chat and ask commands
ed92e44 Dylan O'Keefe <dylanokeefedev@gmail.com> feat(orchestrator): integrate SlotManager for per-turn slot acquisition
f971841 Dylan O'Keefe <dylanokeefedev@gmail.com> feat(inference): add SlotManager for KV-cache slot assignment and eviction
ee7c11d Dylan O'Keefe <dylanokeefedev@gmail.com> feat(persistence): extend assign_slot and release_slot with disk-path tracking
dce32ff Dylan O'Keefe <dylanokeefedev@gmail.com> fix(persistence): archive previous session atomically on create_session
```

All 8 commits authored by Dylan O'Keefe <dylanokeefedev@gmail.com>.
