# Hestia Documentation

This directory contains all documentation for the Hestia project.

## For operators

Getting Hestia running and keeping it healthy:

- **[Runtime setup](guides/runtime-setup.md)** — Install deps, start llama.cpp, and run your first turn.
- **[Environment variables](guides/environment-variables.md)** — Full reference for every `HESTIA_*` env var.
- **[Web dashboard](guides/web-dashboard.md)** — Authentication, navigation, and feature overview for the React admin UI.
- **[Workflows](guides/workflows.md)** — Build, version, and run automated task pipelines.
- **[Browser sessions](guides/browser-sessions.md)** — Warm up Cloudflare-protected sites, manage authenticated logins, and stream browsers from the dashboard.
- **[Voice setup](guides/voice-setup.md)** — Enable Telegram voice messages (STT + TTS).
- **[Email setup](guides/email-setup.md)** — Connect IMAP/SMTP so Hestia can read and draft mail.
- **[Multi-user setup](guides/multi-user-setup.md)** — Run Hestia for more than one person safely.
- **[Security](guides/security.md)** — Threat model, trust presets, and hardening checklist.
- **[Custom tools](guides/custom-tools.md)** — Write your own tools with the `@tool` decorator.
- **[Deploy](deploy/)** — systemd service templates, install script, and config examples.

## For contributors

Understanding why Hestia is built the way it is:

- **[Architecture Decisions](adr/)** — 39 ADRs covering everything from "why Python" to "why FTS5 over vector search."
- **[Design Documents](design/)** — Deep dives on Matrix integration, browser session management, inference analytics, and the revised architecture.
- **[Handoffs](handoffs/)** — Cross-session continuity notes for major subsystem work.
- **[Development Process](development-process/)** — Internal development record: loop specs, review notes, and the Kimi/Cursor workflow. This is project archaeology, not user-facing documentation. Operators and contributors should start with Guides and ADRs instead.

## Reference

- **[Release Notes](releases/)** — Human-facing summaries for each tagged release.
- **[Roadmap](roadmap/future-systems-deferred-roadmap.md)** — Deferred features and future system directions.
- **[Security policy](../SECURITY.md)** — Security policy and responsible disclosure.
- **[Testing](testing/)** — Credentials/secrets handling and manual smoke-test procedures.
- **[Runtime feature testing](runtime-feature-testing.md)** — Quick validation checklist for core capabilities after deployment.
