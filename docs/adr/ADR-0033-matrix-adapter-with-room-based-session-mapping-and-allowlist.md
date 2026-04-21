# ADR-0033: Matrix adapter with room-based session mapping and allowlist

- **Status:** Accepted
- **Date:** 2026-04-12
- **Context:** ADR-0007 positions Matrix as a v1 interface alongside CLI/Telegram.
  The Matrix adapter needs to support automation-first use cases: scripted
  clients, CI-friendly end-to-end tests, and headless operation. Unlike
  Telegram's user-based model, Matrix is room-centric.

- **Decision:**
  1. Use `matrix-nio` (asyncio-first, pure Python) for Matrix protocol support.
     This aligns with Phase 4 asyncio design in the revised architecture.
  2. Session mapping: one Matrix room = one Hestia session. The room ID
     (`!abc:server`) is the `platform_user`. This provides predictable
     isolation for testing and avoids thread-per-session complexity.
  3. Security via `allowed_rooms` whitelist in `MatrixConfig`. Empty list
     denies all inbound (secure default). The bot only responds to rooms
     explicitly listed.
  4. Rate-limit `edit_message` to one call per 1.5 seconds per message,
     same pattern as Telegram. This avoids homeserver abuse flags.
  5. Unencrypted rooms only for v1. E2EE support via `matrix-nio` e2ee
     module is deferred — it requires a crypto store and more complex
     device management.
  6. Status updates use Matrix's `m.replace` relation (message edits).
     The orchestrator's status line pattern works unchanged.
  7. Tool confirmation: deferred to post-v1. For now, destructive tools
     without confirmation callback fail closed with an error message.
     Future: implement "reply YES <nonce>" pattern for approval.

- **Consequences:**
  - Matrix sessions are isolated by room. Two rooms = two sessions even
    if the same human is in both.
  - The bot cannot be used in E2EE rooms until E2EE support is added.
  - CI/integration tests can use a dedicated test room with a test account.
  - No inline buttons for confirmation; users see error messages for
    destructive operations requiring confirmation.
