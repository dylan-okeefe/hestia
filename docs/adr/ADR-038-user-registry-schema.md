# ADR-038: User registry uses four-table schema with separate rooms

- **Status:** Accepted
- **Date:** 2026-05-14
- **Context:** Hestia had no first-class user concept. Platform identifiers (`platform_user`) flowed through sessions, memories, and style profiles, but there was no registry linking a human identity to their platform handles. This caused problems: web auth hardcoded the first user, SOUL.md had hardcoded user descriptions, trust overrides used opaque strings, and group chats conflated all participants into one identity.
- **Decision:** Introduce a four-table schema:
  - `users` — core user record (`display_name`, `role`, `trust_preset`, `notes`)
  - `user_identities` — many-to-one mapping of platform handles to users
  - `rooms` — shared conversation contexts (Telegram groups, Matrix rooms)
  - `room_members` — which users participate in which rooms
- **Consequences:**
  - **Cross-platform identity:** One user can have Telegram + Matrix + CLI identities.
  - **Group chat separation:** Session is scoped to the room; memories/trust/style are scoped to the individual sender.
  - **Dynamic system prompts:** User descriptions move from hardcoded `SOUL.md` to the `users.notes` field, injected per-turn based on who is speaking.
  - **Migration path:** Existing deployments use `hestia migrate-users` to import `allowed_users` / `allowed_rooms` into the registry.
  - **Admin gate:** User creation/deletion requires `role="admin"`, creating a privileged tier.
