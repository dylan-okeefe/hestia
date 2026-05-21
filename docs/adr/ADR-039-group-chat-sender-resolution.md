# ADR-039: Group chats resolve individual sender separately from room

- **Status:** Accepted
- **Date:** 2026-05-14
- **Context:** In Telegram group chats, the adapter previously set `platform_user = chat.id`, discarding the individual sender (`effective_user.id`). This meant all participants shared one session, one memory pool, one trust level, and one style profile. The model could not tell who was speaking.
- **Decision:** Change `IncomingMessageCallback` from 3 args to 4 args, adding `sender_platform_user`:
  - `platform_user` = room/chat ID (used for session scoping and reply routing)
  - `sender_platform_user` = individual sender ID (used for user resolution)
  - In private chats, `sender_platform_user` is `None`.
  - The orchestrator resolves the sender via `UserStore.get_user_by_identity()`.
  - When a known user messages from a group chat, the room and membership are auto-registered.
- **Consequences:**
  - **Breaking change:** All adapters (Telegram, Matrix, CLI) and test mocks updated to accept the 4th parameter.
  - **Backward compatibility:** Private chat behavior is unchanged; `sender_platform_user` defaults to `None`.
  - **Matrix deferred:** Matrix sender extraction is not yet implemented; it passes `None` for now.
  - **Room auto-registration:** Unknown rooms are created on first message from a known user, which could lead to stale room entries if the bot is added to many groups.
