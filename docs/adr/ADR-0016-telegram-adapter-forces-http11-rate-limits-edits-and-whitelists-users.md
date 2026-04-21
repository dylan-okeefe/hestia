# ADR-0016: Telegram adapter forces HTTP/1.1, rate-limits edits, and whitelists users

- **Status:** Accepted
- **Date:** 2026-04-10
- **Context:** The Hermes predecessor used python-telegram-bot with default
  HTTP/2 and had intermittent connection failures. Edit-message spam caused
  Telegram 429 (rate limit) errors. No access control allowed anyone who
  found the bot to interact with it.

- **Decision:**
  1. Force HTTP/1.1 on all Telegram API calls via httpx `http2=False`.
     HTTP/2 multiplexing offers no benefit for a single-user bot and
     causes instability with Telegram's servers.
  2. Rate-limit `edit_message` to at most one call per 1.5 seconds per
     message. Track last-edit time per message ID and sleep if needed.
  3. Introduce `allowed_users` in TelegramConfig: a list of user IDs
     and/or usernames. Empty list = allow all (for testing). Non-empty
     list = whitelist.
  4. TelegramAdapter implements Platform ABC without special-casing.
     The orchestrator is unaware it's talking to Telegram.

- **Consequences:**
  - HTTP/1.1 means slightly higher overhead per request but eliminates
    the intermittent failures seen in Hermes.
  - Rate limiting means status updates during long tool runs may lag
    by up to 1.5 seconds. This is acceptable; the alternative is 429s.
  - The allowed_users whitelist is checked on every incoming message.
    In production with a single user, the list has one entry.
