# L180 — Security & Authorization Hardening — Handoff

**Branch:** `feature/l180-security-hardening`  
**Parent:** `feature/l179-rooms-interactive-nodes`  
**Status:** Complete, validated, ready for next loop

## Summary

Closed the critical authorization gaps identified in the L176-L179 comprehensive audit. Any authenticated user can no longer read other users' sessions, memories, errors, or manage their scheduled tasks.

## Changes

### New files
- `src/hestia/web/dependencies.py` — shared auth dependencies (`require_admin`, `get_current_platform_user`, `RequireOwner`)
- `tests/unit/test_web_authz.py` — 7 authorization and validation tests

### Modified files
- `src/hestia/web/routes/sessions.py` — per-user filtering on `list_sessions` (with `all=true` admin override); ownership checks on `get_turns` and `get_session_messages`
- `src/hestia/web/routes/memory.py` — per-user filtering on `list_memories`; ownership check on `delete_memory`
- `src/hestia/web/routes/scheduler.py` — Pydantic `TaskCreate`/`TaskUpdate` models with `croniter` validation; ownership checks on `update_task`, `delete_task`, `run_task`; `session_id` derived from caller
- `src/hestia/web/routes/errors.py` — admin-only access on all error routes
- `src/hestia/web/routes/users.py` — refactored to use shared `require_admin` from `dependencies.py`
- `src/hestia/memory/store.py` — added `get(memory_id)` method for ownership verification
- `src/hestia/persistence/scheduler.py` — added `notify` parameter to `update_task`
- `tests/unit/test_web_routes.py` — updated 400→422 assertion for missing prompt (Pydantic change)

## Commits

1. `fix(api): enforce per-user authorization on sessions routes`
2. `fix(api): enforce per-user authorization on memory routes`
3. `fix(api): enforce ownership checks on scheduler CRUD`
4. `fix(api): restrict error dashboard to admin users`
5. `feat(api): add Pydantic validation to scheduler endpoints`
6. `refactor(api): extract shared authorization dependencies`
7. `test(api): authorization and validation tests`

## Quality Gates

| Gate | Result |
|------|--------|
| pytest (targeted: web + scheduler + session + memory) | **191 passed** |
| mypy (changed files) | **0 new errors** |
| ruff (changed files) | **0 new issues** |

## Review Notes

- **Auth-disabled mode preserved:** When `request.state.platform_user` is unset (auth disabled or legacy session), ownership checks are skipped. This preserves local/dev behavior.
- **Legacy sessions handled:** `request.state.user_id` may be `None` for legacy sessions — treated as non-admin.
- **`RequireOwner` pattern:** The dependency factory is instantiated with the resource's `platform_user` and called with `(request, ctx)`. This pattern can be reused for future routes.
- **Scheduler `list_tasks` still returns all tasks:** The spec focused on write operations. A future loop may want to filter `list_tasks` by caller as well.
- **Raw SQL in `debug_error` preserved:** This will be addressed in L182 (backend bug fixes).

## Carry-forward

- L181: N+1 queries in `list_users` and `list_sessions` still exist (not in scope for L180)
- L182: Raw SQL in `errors.py:debug_error`, `update_user` null guard, session messages endpoint
