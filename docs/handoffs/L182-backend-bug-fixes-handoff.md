# L182 — Backend Bug Fixes & Cleanup — Handoff

**Branch:** `feature/l182-backend-bug-fixes`  
**Parent:** `feature/l179-rooms-interactive-nodes`  
**Status:** Complete, validated, ready for next loop

## Summary

Fixed six backend correctness and maintainability bugs from the comprehensive audit: null guard preventing field clearing, raw SQL in error dashboard, session messages endpoint returning wrong data, unbounded in-memory state, Telegram ID cast crash, and timeout coercion bug.

## Changes

### Source files
- `src/hestia/persistence/users.py` — removed `v is not None` guard from `update_user` and `update_room`, allowing fields to be cleared to `None` or empty string
- `src/hestia/persistence/sessions.py` — added `get_turn_messages(turn_id)` to encapsulate turn message retrieval
- `src/hestia/web/routes/errors.py` — replaced raw SQL in `debug_error` with `get_turn_messages()`; capped `_resolved_ids` and `_ignored_ids` at 10,000 entries
- `src/hestia/web/routes/sessions.py` — `get_session_messages` now returns actual `messages` array alongside turns
- `src/hestia/workflows/nodes/send_message.py` — validates `timeout_seconds` is non-negative; validates Telegram `platform_user` is numeric before interactive send
- `src/hestia/platforms/notifier.py` — `_send_telegram` and `_send_telegram_interactive` raise `ValueError` on non-numeric chat IDs
- `web-ui/src/components/workflow-editor/NodePropertiesPanel.tsx` — `timeout_seconds` input uses `??` instead of `||`, allowing 0

### Test files
- `tests/unit/persistence/test_user_store.py` — clearing `trust_preset` to `None` and `notes` to `""`
- `tests/unit/test_web_routes.py` — session messages content, error state cap, raw SQL removal
- `tests/unit/workflows/nodes/test_send_message_interactive.py` — Telegram ID validation, timeout validation

## Commits

1. `fix(persistence): allow clearing fields to None/empty in update_user`
2. `refactor(api): remove raw SQL from error dashboard`
3. `feat(api): session messages endpoint returns actual message content`
4. `fix(api): cap in-memory error resolution state size`
5. `fix(workflows): validate platform_user before interactive send`
6. `fix(workflows): allow zero-second timeout and validate input`
7. `test: backend bug fix tests`

## Quality Gates

| Gate | Result |
|------|--------|
| pytest (targeted: user store + web routes + workflow nodes) | **94 passed** |
| mypy (changed source files) | **0 new errors** |
| ruff (changed files) | **0 new issues** (all errors pre-existing baseline) |

## Review Notes

- **Null guard fix:** The `and v is not None` filter was silently discarding intentional clears. Removing it means `trust_preset=None` and `notes=""` are now persisted correctly.
- **Raw SQL removal:** `debug_error` now uses `SessionStore.get_turn_messages()` instead of reaching into `ctx.session_store._db.engine`. The method returns `{"user_message": ..., "final_response": ...}`.
- **Session messages endpoint:** Now returns three top-level keys: `session`, `turns`, `messages`. The frontend `SessionDetail.tsx` may need updating to display the messages array.
- **Error state cap:** `_MAX_RESOLVED = 10_000` with `set.pop()` removes an arbitrary oldest entry. This is defense-in-depth; the sets are only used for in-memory filtering.
- **Telegram validation:** Both the node (`send_message.py`) and the notifier (`notifier.py`) validate numeric IDs. The node validates early for better error messages; the notifier validates as a safety net.
- **Timeout coercion:** TypeScript `??` (nullish coalescing) only falls back on `null`/`undefined`, not `0`. Python validation rejects negative and non-numeric values.

## Carry-forward

- L183: Extract all user-facing text into centralized catalog
- L184: Replace 680 inline styles with shared CSS system
- L185: Make UI responsive on mobile
- L186: Add dark mode
