# L169 — User Registry & Profile Management

**Status:** Spec only  
**Branch:** `feature/l169-user-registry-and-profile` (from `feature/workflow-builder-runtime`)  
**Depends on:** L163 (repo hygiene — for clean base)

## Intent

Hestia has no first-class concept of a "user." Platform identifiers (`platform_user`) flow through sessions, memories, trust overrides, and style profiles, but there is no registry that says "Telegram user 12345678 is Dylan, the admin." This causes several concrete problems:

1. **Web auth hardcodes the first user.** `_get_configured_user` picks `users[0]` from the allowed list — there is no user selection during login. If multiple people share the Telegram bot, only the first can authenticate to the dashboard.

2. **SOUL.md has hardcoded user descriptions** ("Dylan (admin)", "Husband (trusted)") that the model sees but that have no connection to actual platform IDs. The model cannot reliably map "Dylan" to a Telegram ID.

3. **Trust overrides are keyed by opaque strings** (`"telegram:12345678"`) in the config file. There is no place to associate a human name or role with these identifiers.

4. **Memories and style profiles are scoped per `platform_user`** but there is no way for a user to see "what does Hestia know/assume about me" through any interface.

5. **Cross-platform identity is not possible.** If Dylan messages from both Telegram and Matrix, those are two separate `platform_user` identifiers with no linkage — separate sessions, separate memories, separate style profiles.

6. **Group chats conflate all users into one identity.** In Telegram group chats, `platform_user` is set to `str(chat.id)` — the group's ID, not the individual user's ID. The individual `effective_user.id` is available in the Telegram update but gets discarded. This means in a shared group chat, everyone shares one session, one set of memories, one style profile, and one trust level. Hestia cannot tell who is speaking.

This loop adds a `users` table, rooms/group support, a user management API, and the web UI pages to support multi-user login and profile management. New UI pages use OpenUI (`@openuidev/react-ui`) as the component framework.

## Scope

### §0 — UI tooling: OpenUI setup

The existing web-ui (React 18 + Vite) has no component library — pages are built with raw HTML/Tailwind. For L169's new pages (and all future UI work), adopt [OpenUI](https://github.com/thesysdev/openui) as the component framework.

1. Install `@openuidev/react-ui` into `web-ui/`.
2. Define a base component library with Zod schemas for the common elements needed by L169: form inputs, buttons, cards, tables, dropdowns, and status badges.
3. Build all new L169 pages (§4 login flow, §5 profile page, §6 knowledge page) using OpenUI components rather than raw markup.

This is an interim aesthetic choice — the component library can be swapped later if Hestia develops its own design language. The goal for now is consistent, good-looking UI with minimal effort.

**Commit:** `feat(web-ui): add OpenUI component framework and base component library`

### §1 — Users table and store

In `src/hestia/persistence/schema.py`, add:

```python
users = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.String, primary_key=True),          # uuid
    sa.Column("display_name", sa.String, nullable=False),   # "Dylan", "Tim"
    sa.Column("role", sa.String, nullable=False, default="user"),  # admin, trusted, user, child
    sa.Column("trust_preset", sa.String, nullable=True),    # paranoid, household, developer — overrides global trust for this user
    sa.Column("notes", sa.Text, nullable=True),             # free-text notes visible to the model (replaces SOUL.md hardcoded descriptions)
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
)

user_identities = sa.Table(
    "user_identities",
    metadata,
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("platform", sa.String, nullable=False),       # "telegram", "matrix", "cli"
    sa.Column("platform_user", sa.String, nullable=False),  # "12345678", "!roomid:matrix.org"
    sa.Column("verified", sa.Boolean, nullable=False, default=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.PrimaryKeyConstraint("platform", "platform_user"),
    sa.Index("idx_user_identities_user", "user_id"),
)
```

The `user_identities` table is a many-to-one mapping: one user can have multiple platform identities (Telegram + Matrix + CLI). The `(platform, platform_user)` composite key ensures no duplicate mappings.

Add tables for shared conversation contexts (group chats, Matrix rooms):

```python
rooms = sa.Table(
    "rooms",
    metadata,
    sa.Column("id", sa.String, primary_key=True),              # uuid
    sa.Column("platform", sa.String, nullable=False),           # "telegram", "matrix"
    sa.Column("platform_room_id", sa.String, nullable=False),   # Telegram chat.id, Matrix room ID
    sa.Column("display_name", sa.String, nullable=True),        # "Family chat", "Work group"
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.UniqueConstraint("platform", "platform_room_id"),
)

room_members = sa.Table(
    "room_members",
    metadata,
    sa.Column("room_id", sa.String, sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
    sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("joined_at", sa.DateTime, nullable=False),
    sa.PrimaryKeyConstraint("room_id", "user_id"),
)
```

The `rooms` table represents shared conversation contexts. `room_members` maps which users participate in which rooms. This separates the routing concern (replies go to the room) from the identity concern (memories, trust, and style belong to the individual user).

Add `RoomStore` methods to `UserStore` (or a separate store):

```python
async def create_room(self, platform: str, platform_room_id: str, display_name: str | None = None) -> Room
async def get_room_by_platform(self, platform: str, platform_room_id: str) -> Room | None
async def add_room_member(self, room_id: str, user_id: str) -> None
async def remove_room_member(self, room_id: str, user_id: str) -> None
async def get_room_members(self, room_id: str) -> list[User]
async def get_user_rooms(self, user_id: str) -> list[Room]
```

In `src/hestia/persistence/users.py`, create `UserStore`:

```python
class UserStore:
    async def create_user(self, display_name: str, role: str = "user", ...) -> User
    async def get_user(self, user_id: str) -> User | None
    async def get_user_by_identity(self, platform: str, platform_user: str) -> User | None
    async def list_users(self) -> list[User]
    async def update_user(self, user_id: str, **fields) -> User
    async def delete_user(self, user_id: str) -> None
    async def add_identity(self, user_id: str, platform: str, platform_user: str) -> None
    async def remove_identity(self, platform: str, platform_user: str) -> None
    async def get_identities(self, user_id: str) -> list[UserIdentity]
```

Add migration `m003_users_and_rooms` in `persistence/migrations/__init__.py` (covers all four tables).

**Commit:** `feat(persistence): users, user_identities, rooms, room_members tables and stores`

### §2 — Resolve user from platform identity (including group chats)

Add a method to the orchestrator (or a utility) that resolves a `(platform, platform_user)` pair to a `User` object. This is the integration point where the existing `platform_user` string gets connected to real user data:

```python
async def resolve_user(self, platform: str, platform_user: str) -> User | None:
    """Look up the User for a platform identity. Returns None if no mapping exists."""
    return await self._user_store.get_user_by_identity(platform, platform_user)
```

When a user is resolved, their `display_name`, `role`, `notes`, and `trust_preset` become available to:
- The system prompt (replaces hardcoded SOUL.md user descriptions)
- The policy engine (per-user trust overrides from DB instead of config dict)
- The context builder (user-specific prefix)
- Memory scoping (memories can now be scoped to a user ID instead of just platform_user)

For this loop, the resolution is best-effort: if no User mapping exists, behavior is unchanged (falls back to the current `platform_user`-based approach). This ensures backward compatibility.

#### Group chat adapter changes

The Telegram adapter currently sets `platform_user = str(chat.id)` in group chats (line 422 of `telegram_adapter.py`), discarding `effective_user.id`. This must change so that the individual user is identified even in shared rooms.

Update the `on_message` callback signature (in `platforms/base.py`) to accept an optional `sender_platform_user` parameter:

```python
IncomingMessageCallback = Callable[
    [str, str, str, str | None],  # platform, platform_user, text, sender_platform_user
    Awaitable[None],
]
```

In group chats, the adapter now passes:
- `platform_user = str(chat.id)` — used for session scoping and reply routing (unchanged)
- `sender_platform_user = str(effective_user.id)` — used for user resolution

In private chats, `sender_platform_user` is `None` (the `platform_user` already identifies the individual).

The orchestrator uses `sender_platform_user` (when present) to resolve the `User` via the identities table. This means in a group chat:
- The **session** is scoped to the room (all participants share the conversation thread)
- **Memories, trust, and style** are scoped to the individual user who sent the message
- The **system prompt** identifies who is currently speaking ("Current user: Tim (trusted)")

When a message arrives from a group chat and the sender resolves to a known user, auto-register the room and membership if not already tracked:
1. Look up or create a `Room` for `(platform, chat.id)`
2. Add the resolved user to `room_members` if not already a member

**Commit:** `feat(orchestrator): resolve user from platform identity with group chat support`

### §3 — User management API routes

In `src/hestia/web/routes/users.py`:

```
GET    /api/users                     — list all users
POST   /api/users                     — create a user (display_name, role, notes)
GET    /api/users/{id}                — get user details + identities
PUT    /api/users/{id}                — update user (display_name, role, notes, trust_preset)
DELETE /api/users/{id}                — delete user
POST   /api/users/{id}/identities     — add a platform identity (platform, platform_user)
DELETE /api/users/{id}/identities/{platform}/{platform_user} — remove an identity
```

Room management routes (in the same file or `routes/rooms.py`):

```
GET    /api/rooms                     — list all rooms
GET    /api/rooms/{id}                — get room details + members
PUT    /api/rooms/{id}                — update room (display_name)
GET    /api/rooms/{id}/members        — list room members
POST   /api/rooms/{id}/members        — add a user to a room
DELETE /api/rooms/{id}/members/{user_id} — remove a user from a room
```

The create/update endpoints validate `role` against allowed values (`admin`, `trusted`, `user`, `child`). The `trust_preset` field validates against known presets (`paranoid`, `household`, `developer`).

Only admin-role users can create/delete users or change roles. For the initial implementation, check `request.state.platform_user` against the users table and verify role == "admin".

**Commit:** `feat(api): user management CRUD routes`

### §4 — Web UI login with user selection

Currently the login page sends `{ platform: "telegram" }` and the backend sends the code to the first configured user. For multi-user support:

1. Add `GET /api/auth/available-users` endpoint that returns a list of users with at least one identity on a running platform:
   ```json
   [
     {"user_id": "abc", "display_name": "Dylan", "platforms": ["telegram", "matrix"]},
     {"user_id": "def", "display_name": "Tim", "platforms": ["telegram"]}
   ]
   ```

2. Update the login page to show a user-select step before platform selection:
   - Step 1: "Who are you?" — show buttons for each user (by display_name)
   - Step 2: "Verify via..." — show platform options for the selected user
   - Step 3: Enter code (unchanged)

3. Update `AuthManager.request_code` to accept a `user_id` parameter instead of blindly picking the first configured user. Look up the user's identity for the selected platform and send the code there.

4. The resulting web session now carries `user_id` in addition to `platform` and `platform_user`.

**Commit:** `feat(web-ui): user-select login flow`

### §5 — User profile page

Add a `/settings/profile` page (or `/users/{id}` for admin access to any user) that shows:

1. **User info:** Display name (editable), role (admin-editable only), notes (editable)
2. **Connected identities:** List of (platform, platform_user) pairs with ability to add/remove
3. **Rooms:** List of rooms the user is a member of, with display names and other members shown. Admin can manage room membership here.
4. **Trust preset:** Dropdown of presets (admin-editable only)

For the identity management, adding a new identity should go through a verification flow:
- User enters their Telegram ID / Matrix room ID
- System sends a verification message to that identity
- User confirms via the chat platform

For the initial implementation, admin users can add identities without verification (the `verified` field tracks this). Verification flow is a follow-up.

**Commit:** `feat(web-ui): user profile page`

### §6 — "What Hestia knows about you" page

Add a `/settings/knowledge` page that aggregates everything Hestia has associated with the current user:

1. **Memories:** Fetch from MemoryStore filtered by the user's platform identities. Show each memory with content, tags, and creation date. Allow the user to delete individual memories they disagree with.

2. **Style profile:** If style profiling is enabled, show the current style metrics for this user (from StyleStore). This is the "how does Hestia think I communicate" view.

3. **Session history summary:** Show recent sessions (last 10) with session ID, platform, start time, message count. Link to session detail if the sessions page exists.

4. **Handoff summaries:** Show the last 3 session handoff summaries — this is what Hestia "remembers" from previous conversations.

5. **User notes:** The `notes` field from the users table, editable inline. This is what gets injected into the system prompt as the user description (replacing SOUL.md hardcoded entries).

The key UX principle: transparency. Users should be able to see and correct everything Hestia has inferred or stored about them.

**Commit:** `feat(web-ui): knowledge review page`

### §7 — Inject user context into system prompt

In `context/builder.py` or the orchestrator assembly, when a user is resolved (§2), build a user-context prefix:

```
Current user: Dylan (admin)
Notes: operator, technical, security-minded. No SaaS upsell as default.
```

This replaces the hardcoded SOUL.md user descriptions. The SOUL.md `## Users` section should be reduced to a generic policy statement ("Respect user roles and trust levels") rather than naming specific people.

When no user is resolved (backward compat), fall back to the existing behavior.

**Commit:** `feat(context): inject resolved user context into system prompt`

### §8 — Migration path from config to DB

For existing deployments, provide a one-time migration utility that:

1. Reads `TelegramConfig.allowed_users` and `MatrixConfig.allowed_rooms`
2. Creates User records for each unique identity
3. Links platform identities to those users
4. The first user in each list gets `role="admin"` (matching current `_get_configured_user` behavior)
5. Copies `trust_overrides` from config into user `trust_preset` fields

This should be a CLI command: `hestia migrate-users` that is idempotent (safe to run multiple times).

**Commit:** `feat(cli): migrate-users command for config-to-DB user migration`

### §9 — Tests

1. **UserStore CRUD:** Create, read, update, delete users. Add/remove identities. Verify composite key constraint.
2. **Room CRUD:** Create rooms, add/remove members, verify unique constraint on (platform, platform_room_id).
3. **Identity resolution:** Create user with Telegram identity. Call `resolve_user("telegram", "12345678")`. Assert returns correct user.
4. **Cross-platform resolution:** Create user with both Telegram and Matrix identities. Resolve from either. Assert same user.
5. **Group chat resolution:** Simulate a message from a group chat with `sender_platform_user` set. Assert the individual user is resolved, not the room. Assert room and membership auto-created.
6. **Auth flow with user selection:** Mock available-users endpoint. Select a user. Verify code sent to correct identity.
7. **Knowledge page data:** Create user, add memories, create sessions. Verify knowledge endpoint returns aggregated data.
8. **Migration utility:** Set up config with allowed_users. Run migrate-users. Verify User and UserIdentity records created.
9. **OpenUI components:** Verify the base component library renders without errors. Snapshot tests for profile and knowledge pages.

**Commit:** `test: user registry and profile management`

## Evaluation

- Users table exists with display_name, role, trust_preset, and notes
- Platform identities are linked to users (many identities per user)
- Rooms and room_members tables track shared conversation contexts (group chats)
- In group chats, the individual sender is identified and resolved (not conflated with the room)
- Rooms are auto-registered when a known user messages from a group chat
- Web login shows user selection when multiple users exist
- User profile page allows editing name, notes, viewing identities, and viewing room memberships
- Knowledge page shows memories, style profile, session history, and handoff summaries
- System prompt includes resolved user context instead of hardcoded SOUL.md descriptions
- Existing deployments can migrate with `hestia migrate-users`
- All new UI pages use OpenUI components from the base component library

## Acceptance

- `pytest tests/unit/ -q` green
- Frontend tests pass
- `mypy src/hestia` reports 0 new errors
- `ruff check src/ tests/` clean on changed files

## Notes

This is a large loop. If Kimi needs to split it, the natural break points are:

- **L169a:** §0-§1 (OpenUI setup + backend: tables, stores) — no functional UI changes
- **L169b:** §2-§3 (user resolution + adapter group chat changes + API routes)
- **L169c:** §4-§6 (login flow + profile page + knowledge page)
- **L169d:** §7-§9 (system prompt injection + migration utility + tests)

### L164 status

L164 (Execution Refactor) was absorbed into the L165-L168 implementation batch. The `_handle_tool_calls` method exists in `execution.py` and the deduplication is complete. No standalone handoff was written. The kimi-loop-log should be updated to reflect this.
