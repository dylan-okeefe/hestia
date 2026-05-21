# L181 — Performance & Resource Cleanup — Handoff

**Branch:** `feature/l181-performance-cleanup`  
**Parent:** `feature/l179-rooms-interactive-nodes`  
**Status:** Complete, validated, ready for next loop

## Summary

Fixed three performance/resource issues from the comprehensive audit: N+1 queries in list endpoints, unbounded memory growth in the workflow response store, and connection leaks in platform notifiers.

## Changes

### Source files
- `src/hestia/persistence/users.py` — added `get_identities_for_users()` and `get_rooms_for_users()` batch methods
- `src/hestia/persistence/sessions.py` — added `count_turns_for_sessions()` batch method
- `src/hestia/web/routes/users.py` — uses batch methods in `list_users` (3 queries total regardless of user count)
- `src/hestia/web/routes/sessions.py` — uses batch method in `list_sessions` (2 queries total regardless of session count)
- `src/hestia/workflows/response_store.py` — added `timeout_seconds` field, lazy background sweep task that cancels stale requests after 2× timeout, `stop()` for clean shutdown
- `src/hestia/platforms/notifier.py` — cached Telegram `Bot` instance via `_get_telegram_bot()`; `close()` releases it; Matrix uses `uuid.uuid4().hex[:16]` for unique `txn_id`
- `src/hestia/web/routes/errors.py` — error aggregation filters by caller ownership (coupled with L180 admin restriction)

### Test files
- `tests/unit/persistence/test_user_store.py` — batch query tests for identities and rooms
- `tests/unit/test_session_store_turns.py` — batch turn count test
- `tests/unit/workflows/test_response_store.py` — TTL sweep and stop tests
- `tests/unit/platforms/test_notifier.py` — Telegram cache reuse and Matrix txn_id uniqueness tests

## Commits

1. `perf(api): batch identities and rooms queries in list_users`
2. `perf(api): batch turn count query in list_sessions`
3. `fix(workflows): add TTL cleanup to WorkflowResponseStore`
4. `fix(platforms): cache Telegram Bot instance to prevent connection leaks`
5. `fix(platforms): use random txn_id for Matrix notifications`
6. `fix(api): filter error aggregation by caller ownership`
7. `test: performance and resource cleanup tests`

## Quality Gates

| Gate | Result |
|------|--------|
| pytest (targeted: persistence + workflow + platform tests) | **61 passed, 1 warning** |
| mypy (changed source files) | **0 new errors** |
| ruff (changed files) | **0 new issues** (2 pre-existing B017 in untouched lines) |

## Review Notes

- **Batch methods use SQLAlchemy core `in_()` clauses** — requires the schema tables to be SQLAlchemy Core `Table` objects, which they are (`user_identities`, `rooms`, `room_members`, `turns` imported from `schema.py`).
- **Sweep task starts lazily** — `WorkflowResponseStore` doesn't create the background task until the first `create()` call, avoiding unnecessary overhead for stores that are instantiated but never used.
- **Telegram bot shutdown** — `close()` calls `await self._telegram_bot.shutdown()`, which is the python-telegram-bot v20+ API for closing the internal httpx client.
- **Matrix txn_id** — `uuid.uuid4().hex[:16]` gives ~2^64 possible values, collision probability is negligible.
- **Error aggregation ownership** — Since L180 restricts error routes to admin users, the ownership filter in `list_errors` is primarily defense-in-depth. If the admin restriction is ever relaxed, the filter ensures non-admins only see their own errors.

## Carry-forward

- L182: `update_user` null guard, raw SQL in `debug_error`, session messages endpoint, `send_message` validation
