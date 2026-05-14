# Multi-user setup guide

Hestia supports multiple distinct users across platforms (CLI, Telegram, Matrix) with per-user memory scoping, trust profiles, and identity management.

This guide covers configuring and managing users in Hestia.

---

## Quick start

If you already have `allowed_users` (Telegram) or `allowed_rooms` (Matrix) in your config, run the migration to create user records:

```bash
hestia migrate-users
```

This creates a `User` record for each configured identity, links them to platform identities, and assigns the first user `role="admin"`.

---

## User registry

Hestia stores users in a database-backed registry with four tables:

- **`users`** — core user record: `display_name`, `role`, `trust_preset`, `notes`
- **`user_identities`** — platform identities linked to users (one user can have many)
- **`rooms`** — shared conversation contexts (Telegram groups, Matrix rooms)
- **`room_members`** — which users belong to which rooms

### Roles

| Role | Permissions |
|------|-------------|
| `admin` | Create/delete users, change roles, manage rooms, edit trust presets |
| `trusted` | Standard user with elevated trust preset |
| `user` | Standard user |

> **Note:** `child` role is deferred — not yet implemented.

### Trust presets

| Preset | Auto-approve tools | Scheduler shell | Subagent shell/write | Use case |
|--------|-------------------|-----------------|----------------------|----------|
| `paranoid` | None | No | No | Guests, untrusted users, default |
| `household` | `terminal`, `write_file` | Yes | Yes | Trusted family members |
| `developer` | All (`*`) | Yes | Yes | Dev/testing only |

Trust presets are stored per-user in the `users.trust_preset` column and override the global default at runtime.

---

## Managing users

### Web dashboard

The dashboard provides a **Profile** page (`/profile`) and **Knowledge** page (`/knowledge`) for each user:

- **Profile** — view/edit display name and notes, manage linked identities, see room memberships
- **Knowledge** — view memories, style profile, session history, and user notes (what Hestia knows about you)

Admin users can also manage other users via the API.

### API

All routes require Bearer token auth (except where noted).

#### List users
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8765/api/users
```

#### Create a user (admin only)
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Alice", "role": "user", "trust_preset": "household", "notes": "Likes concise answers"}' \
  http://localhost:8765/api/users
```

#### Add an identity to a user (admin only)
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"platform": "telegram", "platform_user": "12345678"}' \
  http://localhost:8765/api/users/$USER_ID/identities
```

#### List rooms
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8765/api/rooms
```

#### Add a member to a room (admin only)
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "$USER_ID"}' \
  http://localhost:8765/api/rooms/$ROOM_ID/members
```

---

## Platform allow-lists

Platform allow-lists (`telegram.allowed_users`, `matrix.allowed_rooms`) still control **access** — who can message the bot. The user registry controls **identity** — who Hestia thinks is speaking.

### Telegram

```python
from hestia.config import HestiaConfig, TelegramConfig

config = HestiaConfig(
    telegram=TelegramConfig(
        bot_token="YOUR_TOKEN",
        allowed_users=[
            "123456789",           # numeric user ID (most reliable)
            "alice",               # username (without @)
            "bob",                 # exact username
            "family_*",            # wildcard: matches family_alice, family_bob, etc.
            "admin_?",             # wildcard: matches admin_a, admin_b, etc.
        ],
    ),
)
```

**Matching rules:**
- Numeric IDs are matched exactly.
- Usernames are matched case-insensitively.
- Wildcards use Unix shell-style syntax: `*` matches any sequence, `?` matches one character.

### Matrix

```python
from hestia.config import HestiaConfig, MatrixConfig

config = HestiaConfig(
    matrix=MatrixConfig(
        homeserver="https://matrix.org",
        user_id="@hestia-bot:matrix.org",
        access_token="YOUR_TOKEN",
        allowed_rooms=[
            "!abc123:matrix.org",           # exact room ID
            "#family-chat:matrix.org",      # exact room alias
            "#ops-*:matrix.org",            # wildcard
        ],
    ),
)
```

---

## Group chats

In Telegram groups, Hestia now identifies the **individual sender** separately from the **room**:

- **Session** is scoped to the room (`chat.id`) — all participants share the conversation thread
- **Memories, trust, and style** are scoped to the individual sender (`effective_user.id`)
- The **system prompt** identifies who is currently speaking (e.g., "Current user: Alice (trusted)")

When a known user messages from a group chat, Hestia auto-registers the room and adds the user as a member if not already tracked.

> **Matrix group rooms:** Follow the same pattern — the room ID is used for session scoping, and the sender's Matrix ID is used for user resolution.

---

## User notes and system prompt

The `notes` field on a user record is injected into the system prompt at runtime:

```
Current user: Dylan (admin)
Notes: operator, technical, security-minded. No SaaS upsell as default.
```

This replaces the hardcoded user descriptions that previously lived in `SOUL.md`. Users can view and edit their own notes via the **Knowledge** page.

---

## Migrating from config-based users

If you previously used `trust_overrides` with hardcoded `platform:platform_user` keys, migrate to the registry:

```bash
hestia migrate-users
```

This command is idempotent — safe to run multiple times. It will:

1. Read `TelegramConfig.allowed_users` and `MatrixConfig.allowed_rooms`
2. Create `User` records for each unique identity
3. Link platform identities to those users
4. Assign `role="admin"` to the first user in each list
5. Skip identities that already exist in the registry

After migration, you can remove `trust_overrides` from your config and manage trust via the user registry instead.

---

## Troubleshooting

### "Not authorized" on Telegram

Check that your numeric user ID or username is in `allowed_users`. Numeric IDs are more reliable than usernames because usernames can change.

To find your Telegram user ID, message `@userinfobot`.

### Messages not received on Matrix

Check that the room ID or alias is in `allowed_rooms`. Room IDs start with `!`; aliases start with `#`. Both must include the server part after `:`.

To find a room ID, open the room settings in Element and look under "Advanced".

### User not resolved in group chats

The user must have a linked identity matching their platform ID. For Telegram groups, this means the `effective_user.id` must match a `user_identities.platform_user` entry. Run `hestia migrate-users` or add the identity manually via the API.

### "Admin access required" when creating users

Only users with `role="admin"` can create, update, or delete other users. The first user created by `migrate-users` gets admin. If you need to promote another user, update their role via the API:

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}' \
  http://localhost:8765/api/users/$USER_ID
```

---

## Single-user deployments

If you are the only user, you don't need to think about the registry. Just run `hestia migrate-users` once after setup and set your trust preset:

```bash
hestia migrate-users
```

Then visit `/profile` in the dashboard to view your record and `/knowledge` to see what Hestia knows about you.
