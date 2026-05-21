# ADR-034: Web Dashboard Authentication via Chat 2FA

- **Status:** Accepted
- **Date:** 2026-05-01
- **Context:** The web dashboard had no authentication. Any process on localhost
  could hit the API, read sessions, accept proposals, and view config. DES-3
  flagged this as a design issue. A traditional login system (user accounts,
  password hashing, reset flows) is disproportionate for a local-first assistant
  that already has authenticated bidirectional channels to its users via Telegram
  and Matrix.

- **Decision:**
  1. Authenticate web users by sending a one-time code through their already-
     connected chat platform (Telegram or Matrix).
  2. Use opaque session tokens stored in an in-memory dict on the server. No
     JWTs — they add complexity (signing keys, refresh tokens, revocation
     blocklists) with zero benefit for a single-process architecture.
  3. No OAuth or Telegram Login Widget — the widget requires a public domain
     and HTTPS; Hestia runs on localhost. Matrix has no equivalent widget.
  4. Auth is enforced at the FastAPI API layer via middleware. Static files
     (the SPA bundle) remain unauthenticated — the SPA itself is not sensitive.
  5. Session lifetime defaults to 72 hours. Code expiry is 5 minutes. Rate
     limiting blocks after 5 failed attempts in 10 minutes from the same IP.

- **Consequences:**
  - Users authenticate without creating a new password. The chat adapter already
    knows their identity (`platform` + `platform_user`), so the web session
    inherits it.
  - A server restart invalidates all sessions. This is acceptable for local-first
    use; persistence would add unnecessary complexity.
  - Multi-user support is a straightforward future extension: add a
    `platform_user` field to `request-code` and send to arbitrary users.
  - When `auth_enabled=False`, all middleware checks are bypassed and the
    dashboard behaves exactly as before.
