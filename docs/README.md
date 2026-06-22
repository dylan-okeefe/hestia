# Hestia Documentation

This directory contains all documentation for the Hestia project.

## For operators

Getting Hestia running and keeping it healthy:

- **[Guides](guides/)** — Step-by-step walkthroughs for setup, voice, email, multi-user,
  security, browser sessions, workflows, the web dashboard, and custom tools.
- **[Environment variables](guides/environment-variables.md)** — Full reference for every `HESTIA_*` env var.
- **[Deploy](deploy/)** — systemd service templates, install script, and config examples.

## For contributors

Understanding why Hestia is built the way it is:

- **[Architecture Decisions](adr/)** — 49 ADRs covering everything from "why Python" to "why FTS5 over vector search."
- **[Design Documents](design/)** — Deep dives on Matrix integration, browser session management, inference analytics, and the revised architecture.
- **[Handoffs](handoffs/)** — Cross-session continuity notes for major subsystem work.
- **[Development Process](development-process/)** — Internal development record: loop specs, review notes, and the Kimi/Cursor workflow. This is project archaeology, not user-facing documentation. Operators and contributors should start with Guides and ADRs instead.

## Reference

- **[Release Notes](releases/)** — Human-facing summaries for each tagged release.
- **[Roadmap](roadmap/future-systems-deferred-roadmap.md)** — Deferred features and future system directions.
- **[Security policy](../SECURITY.md)** — Security policy and responsible disclosure.
- **[Testing](testing/)** — Credentials/secrets handling and manual smoke-test procedures.
- **[Runtime feature testing](runtime-feature-testing.md)** — Quick validation checklist for core capabilities after deployment.
