# L180 — Security & Authorization Hardening

**Status:** Spec only  
**Branch:** `feature/l180-security-hardening` (from `feature/l179-rooms-interactive-nodes`)  
**Depends on:** L176–L179

## Intent

The audit found that while the global `AuthMiddleware` enforces authentication on all `/api/*` routes, **none of the new routes enforce that the caller can only access their own data.** Any authenticated user can read all sessions, all memories, all conversation transcripts, all system errors, and create/delete scheduled tasks for any session. This is a catastrophic privacy and security hole for any deployment beyond localhost.

This loop closes those gaps by adding per-user authorization to all personal data routes and input validation to the scheduler API.

## Scope

### §0 — Add per-user authorization to sessions API

**Why:** `GET /api/sessions` returns every session in the system. `GET /api/sessions/{id}/messages` returns any conversation transcript. Any logged-in user can spy on every other user's conversations.

In `src/hestia/web/routes/sessions.py`:

1. `list_sessions`: Filter by the authenticated user's `platform_user` from `request.state`. Admin users can pass an optional `all=true` query param to see everything.
   ```python
   caller_platform_user = request.state.platform_user
   if not all_flag or caller_role != "admin":
       platform_user = caller_platform_user
   ```
2. `get_turns` and `get_session_messages`: Verify the session belongs to the caller before returning turns.
   ```python
   session = await ctx.session_store.get_session(session_id)
   if session.platform_user != request.state.platform_user:
       raise HTTPException(status_code=403, detail="Access denied")
   ```

**Commit:** `fix(api): enforce per-user authorization on sessions routes`

### §1 — Add per-user authorization to memory API

**Why:** `GET /api/memory` returns all memories. `DELETE /api/memory/{id}` deletes any memory by ID. A user can wipe another user's learned facts.

In `src/hestia/web/routes/memory.py`:

1. `list_memories`: Default `platform_user` filter to the caller's `platform_user` from `request.state`. Admin can override.
2. `delete_memory`: Before deleting, verify the memory belongs to the caller:
   ```python
   mem = await ctx.app.memory_store.get(memory_id)
   if mem.platform_user != request.state.platform_user:
       raise HTTPException(status_code=403, detail="Access denied")
   ```

**Commit:** `fix(api): enforce per-user authorization on memory routes`

### §2 — Add ownership checks to scheduler API

**Why:** `POST /api/scheduler/tasks` accepts `session_id` from the payload with no validation. An attacker can attach tasks to arbitrary sessions. `DELETE` and `PUT` don't check ownership.

In `src/hestia/web/routes/scheduler.py`:

1. `create_task`: Derive `session_id` from the authenticated user's `platform_user` instead of accepting it from the payload. Or validate that the provided `session_id` belongs to the caller.
2. `update_task` and `delete_task`: Fetch the task first, verify `session_id` matches the caller's session before allowing modifications.
3. `run_task`: Same ownership check before triggering.

**Commit:** `fix(api): enforce ownership checks on scheduler CRUD`

### §3 — Add role-based access to errors API

**Why:** `GET /api/errors` exposes system errors that may contain stack traces, file paths, and user data. Any authenticated user can see them.

In `src/hestia/web/routes/errors.py`:

1. `list_errors`: Only admin users can access. Non-admins get 403.
2. `resolve_error`, `ignore_error`, `debug_error`: Same admin-only check.
3. The errors nav link in the frontend is already admin-gated; make the backend match.

**Commit:** `fix(api): restrict error dashboard to admin users`

### §4 — Add Pydantic validation to scheduler API

**Why:** `POST /api/scheduler/tasks` accepts raw `dict[str, Any]`. No validation means invalid cron strings are stored silently and only fail at scheduler runtime.

In `src/hestia/web/routes/scheduler.py`:

1. Define Pydantic models:
   ```python
   class TaskCreate(BaseModel):
       prompt: str
       description: str | None = None
       cron_expression: str | None = None
       enabled: bool = True
       notify: bool = False
   
   class TaskUpdate(BaseModel):
       prompt: str | None = None
       description: str | None = None
       cron_expression: str | None = None
       enabled: bool | None = None
       notify: bool | None = None
   ```
2. Validate `cron_expression` with `croniter` or regex if provided.
3. Replace raw dict payloads with typed models.

**Commit:** `feat(api): add Pydantic validation to scheduler endpoints`

### §5 — Extract shared authorization helper

**Why:** Authorization logic is copy-pasted across routes. A shared helper reduces duplication and prevents future gaps.

In `src/hestia/web/auth.py` or a new `src/hestia/web/dependencies.py`:

1. Create `RequireOwner` dependency that:
   - Reads `request.state.platform_user`
   - Compares against a resource's `platform_user` field
   - Returns 403 if mismatch
   - Skips check if caller is admin
2. Create `RequireAdmin` dependency (extract from `users.py`).

**Commit:** `refactor(api): extract shared authorization dependencies`

### §6 — Tests

1. **Sessions auth test:** Authenticate as User A. Try to list sessions. Assert only User A's sessions returned. Try to access User B's session messages. Assert 403.
2. **Memory auth test:** Authenticate as User A. Create memory for User B. Try to delete it. Assert 403.
3. **Scheduler auth test:** Authenticate as User A. Try to create task with User B's session_id. Assert 403 or task created for User A instead.
4. **Errors auth test:** Authenticate as non-admin. Try to access `/api/errors`. Assert 403.
5. **Scheduler validation test:** POST task with invalid cron `"not-a-cron"`. Assert 422.

**Commit:** `test(api): authorization and validation tests`

## Evaluation

- Sessions API only returns the caller's sessions (unless admin)
- Memory API only returns/creates/deletes the caller's memories
- Scheduler API validates ownership and input data
- Error dashboard is admin-only on both frontend and backend
- Shared authorization helpers exist and are used

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L180`
