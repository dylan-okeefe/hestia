# ADR-007: No web UI in v1

- **Status:** Superseded
- **Date:** 2026-04-09
- **Context:** Building a good web UI is a project in itself. CLI and chat
  platforms (Telegram, Matrix) provide sufficient interfaces for a v1 personal
  assistant. Web UIs add security surface area (CSRF, XSS, auth).
- **Decision:** No web UI in v1. CLI for local testing, Telegram/Matrix for remote
  access. A read-only status dashboard is a possible future addition.
- **Consequences:** Users must use existing chat clients; no custom web interface
  for interacting with the agent.

> **Superseded by** L118–L191 (web dashboard with auth, CRUD, workflow editor,
> dark mode, responsive design). The v0.12.0 release ships a 14-page React SPA
> that replaces this decision entirely.
