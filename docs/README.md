# Hestia Documentation

This directory contains all documentation for the Hestia project.

## For operators

Getting Hestia running and keeping it healthy:

- **[Guides](guides/)** — Step-by-step walkthroughs for setup, voice, email, multi-user, security, and tuning.
- **[Environment Variables](guides/environment-variables.md)** — Full reference for every `HESTIA_*` env var.
- **[Deploy](deploy/)** — systemd service templates, install script, and config examples.

## For contributors

Understanding why Hestia is built the way it is:

- **[Architecture Decisions](adr/)** — 33 ADRs covering everything from "why Python" to "why FTS5 over vector search."
- **[Design Documents](design/)** — Deep dives on Matrix integration, the phase-8+ roadmap, and the revised architecture.
- **[Development Process](development-process/)** — Internal development record: loop specs, review notes, and the Kimi/Cursor workflow. This is project archaeology, not user-facing documentation. Operators and contributors should start with Guides and ADRs instead.

## Reference

- **[Release Notes](releases/)** — Human-facing summaries for each tagged release.
- **[Roadmap](roadmap/future-systems-deferred-roadmap.md)** — Deferred features and future system directions.
- **[Security](../SECURITY.md)** — Security policy and responsible disclosure.
- **[Testing](testing/)** — Credentials/secrets handling and manual smoke-test procedures.
