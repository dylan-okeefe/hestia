# L170 — L169 Backend Hardening & Data Integrity

**Status:** Spec only  
**Branch:** `feature/l170-l169-backend-hardening` (from `feature/l169-user-registry`)  
**Depends on:** L169 (user registry implementation on branch)

## Intent

The L169 user-registry branch introduced backend bugs that corrupt data, break type safety, and block stated features. These are not presentation issues — they affect the correctness of the database, the auth flow, and the orchestrator layer. Fixing them before any UI rewrite ensures the foundation is solid; rebuilding UI on top of buggy data logic would waste effort.

Specifically:
- The migration utility misclassifies Matrix rooms as users, which is the root cause of the confusing login screen and wrong data display.
- The `child` role exists in the schema and documentation but cannot be assigned through the API.
- `resolved_user: Any | None` defeats mypy across the entire orchestrator layer, hiding real type errors.
- Deleting a user orphans `room_members` rows, causing phantom data and potential join errors.

## Scope

### §0 — Fix migration utility: distinguish rooms from users

**Why:** `src/hestia/commands/users.py` iterates platform users and creates User records for Matrix room IDs (e.g. `!JobaAjDMsxsiOaenRV:matrix.org`). These are rooms, not people. This is why four "users" appear on the login screen when only two are real people.

In `src/hestia/commands/users.py` (the `migrate-users` command):

1. Before creating a User record, inspect the `platform_user` string:
   - Matrix IDs starting with `!` → create a `Room` record in the `rooms` table.
   - Matrix IDs starting with `@` → create a `User` record.
   - Telegram IDs (numeric strings) → create a `User` record.
2. For room records, set `platform_room_id` to the Matrix room ID and `display_name` to `None` (or the room alias if resolvable).
3. Link the first admin user to any auto-created rooms via `room_members` so they don't appear as login options.
4. Make the command idempotent: if a room already exists for `(platform, platform_room_id)`, skip it.

**Commit:** `fix(cli): classify Matrix room IDs as rooms during user migration`

### §1 — Add `child` role to API validation

**Why:** The schema and SOUL.md reference a `child` role for restricted access, but `src/hestia/web/routes/users.py` defines `_ROLES = {"admin", "trusted", "user"}`. Creating a child user via the API returns a 422 validation error, which silently blocks a documented feature.

In `src/hestia/web/routes/users.py`:

1. Update `_ROLES` to `{"admin", "trusted", "user", "child"}`.
2. Update any Pydantic/FastAPI validation models that restrict role values (e.g. `UserCreate`, `UserUpdate` schemas) to include `"child"`.
3. Add a test that creates a user with `role="child"` and asserts 200.

**Commit:** `fix(api): include child role in user role validation set`

### §2 — Fix `resolved_user` typing in TurnContext

**Why:** `src/hestia/orchestrator/types.py` adds `resolved_user: Any | None = None`. The `Any` type defeats type checking across the entire orchestrator layer — every downstream consumer must guess, cast, or ignore the type. Using the actual `User` type lets mypy catch misuse at build time.

In `src/hestia/orchestrator/types.py`:

1. Import `User` from `hestia.persistence.users` (or the appropriate types module).
2. Change `resolved_user: Any | None = None` to `resolved_user: User | None = None`.
3. Fix any mypy errors that surface in files consuming `TurnContext.resolved_user` (likely in `orchestrator/orchestrator.py`, `context/builder.py`, and policy modules).
4. Remove the `Any` import if it becomes unused.

**Commit:** `refactor(orchestrator): replace Any with User for resolved_user in TurnContext`

### §3 — Cascade `room_members` on user deletion

**Why:** `UserStore.delete_user` cascades to `user_identities` but not `room_members`. Deleting a user leaves orphaned membership rows that accumulate silently and can cause join errors or phantom data later.

In `src/hestia/persistence/users.py`:

1. In `delete_user`, after the `user_identities` cascade and before deleting the user row, add:
   ```python
   await conn.execute(
       sa.delete(room_members).where(room_members.c.user_id == user_id)
   )
   ```
2. Add a test: create a user, add them to a room, delete the user, then assert `get_room_members(room_id)` returns an empty list.

**Commit:** `fix(persistence): cascade room_members when deleting a user`

### §4 — Tests

1. **Migration classification test:** Mock config with `allowed_rooms = ["!room:matrix.org"]` and `allowed_users = ["@user:matrix.org"]`. Run `migrate-users`. Assert one Room and one User created.
2. **Child role creation test:** POST `/api/users` with `{"display_name": "Kid", "role": "child"}`. Assert 200 and response role is `"child"`.
3. **Resolved user type test:** Create a TurnContext with a mocked User. Assert `context.resolved_user.display_name` is accessible without casting.
4. **Delete user cascade test:** Create user, add identity, add to room. Delete user. Assert room_members table has zero rows for that user_id.

**Commit:** `test: backend hardening for L169 data integrity`

## Evaluation

- Matrix room IDs in config are migrated to `rooms` table, not `users` table
- `role="child"` can be created and updated via the API without validation errors
- `TurnContext.resolved_user` is typed as `User | None`; mypy reports zero errors in changed orchestrator files
- Deleting a user removes all related `room_members` rows
- Migration command remains idempotent

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files
- `.kimi-done` includes `LOOP=L170`
