# ADR-0007: No web UI in v1

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Building a good web UI is a project in itself. CLI and chat
  platforms (Telegram, Matrix) provide sufficient interfaces for a v1 personal
  assistant. Web UIs add security surface area (CSRF, XSS, auth).
- **Decision:** No web UI in v1. CLI for local testing, Telegram/Matrix for remote
  access. A read-only status dashboard is a possible future addition.
- **Consequences:** Users must use existing chat clients; no custom web interface
  for interacting with the agent.
