# Multi-user setup guide

Hestia is designed for personal deployments — one operator, one machine. However, it supports multiple distinct users across platforms (CLI, Telegram, Matrix) with per-user memory scoping and trust profiles.

This guide covers configuring Hestia for household or small-team deployments where multiple people share the same instance.

---

## Security model

Hestia's multi-user security is **opt-in and whitelist-based**:

- **Empty allow-list = deny all.** If you don't configure `allowed_users` (Telegram) or `allowed_rooms` (Matrix), no one can access Hestia through that platform.
- **Per-user memory scoping.** Memories saved by one user are not visible to another user. Each memory is tagged with the user's `platform:platform_user` identity.
- **Per-user trust overrides.** You can grant different trust levels to different users. A household member might get `household()` trust while a guest gets `paranoid()`.

> **Warning:** Hestia is not designed for multi-tenant SaaS deployments. The security model assumes the operator controls the hardware and trusts the users they allow. Do not expose Hestia to the open internet without platform-level allow-lists.

---

## Platform allow-lists

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
- Wildcards use Unix shell-style syntax: `*` matches any sequence, `?` matches one character, `[seq]` matches any character in `seq`.
- Invalid entries are logged as warnings at startup but do not block the bot.

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
            "#ops-*:matrix.org",            # wildcard: matches #ops-deploy, #ops-alerts, etc.
        ],
    ),
)
```

**Matching rules:**
- Room IDs and aliases are matched exactly (case-sensitive).
- Wildcards use the same shell-style syntax as Telegram.
- Entries without a `:` (server part) or `!`/`#` prefix are warned at startup.

---

## Trust profiles per user

Use `trust_overrides` to grant different users different levels of autonomy:

```python
from hestia.config import HestiaConfig, TrustConfig

config = HestiaConfig(
    trust=TrustConfig.household(),  # default for unlisted users
    trust_overrides={
        "telegram:alice": TrustConfig.household(),
        "telegram:bob": TrustConfig.paranoid(),
        "matrix:#family-chat:matrix.org": TrustConfig.household(),
        "cli:default": TrustConfig.developer(),
    },
)
```

Keys are `platform:platform_user`. The platform matches the adapter name (`telegram`, `matrix`, `cli`). The `platform_user` is the Telegram user ID/username, Matrix room ID/alias, or CLI default user.

### Trust presets

| Preset | Auto-approve tools | Scheduler shell | Subagent shell/write | Use case |
|--------|-------------------|-----------------|----------------------|----------|
| `paranoid()` | None | No | No | Guests, untrusted users, default |
| `household()` | `terminal`, `write_file` | Yes | Yes | Trusted family members |
| `developer()` | All (`*`) | Yes | Yes | Dev/testing only |
| `prompt_on_mobile()` | None (confirmation prompt) | Yes | Yes | Phone-controlled confirmations |

---

## Troubleshooting

### "Not authorized" on Telegram

Check that your numeric user ID or username is in `allowed_users`. Numeric IDs are more reliable than usernames because usernames can change.

To find your Telegram user ID, message `@userinfobot`.

### Messages not received on Matrix

Check that the room ID or alias is in `allowed_rooms`. Room IDs start with `!`; aliases start with `#`. Both must include the server part after `:`.

To find a room ID, open the room settings in Element and look under "Advanced".

### Unexpected tool denials

If a user reports that tools like `terminal` or `write_file` are blocked:

1. Check the active trust profile: `hestia config` shows the default trust preset.
2. Check if a per-user override exists in `trust_overrides`.
3. Remember that `paranoid()` (the default) blocks all confirmation-required tools on headless platforms.
4. Scheduler and subagent contexts have additional restrictions even under `household()`.

### Memory not visible across sessions

This is by design. Memories are scoped to the user identity (`platform:platform_user`). If you log in as a different Telegram user or switch Matrix rooms, you will see different memories. Use `trust_overrides` to control which users can access which tools, but memory isolation is always enforced.

---

## Single-user deployments

If you are the only user, you don't need `trust_overrides`. Just set your platform allow-list and choose a default trust preset:

```python
config = HestiaConfig(
    telegram=TelegramConfig(
        bot_token="YOUR_TOKEN",
        allowed_users=["YOUR_USER_ID"],
    ),
    trust=TrustConfig.household(),
)
```

This is the recommended configuration for personal deployments.
