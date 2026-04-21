# ADR-0002: Package manager is `uv`

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Python packaging is notoriously painful. Poetry is slow, pip lacks
  lockfiles by default, and conda is overkill for a single-package project. We
  need fast installs, lockfile-by-default, and a good dev loop.
- **Decision:** Use `uv` (Astral's Python packaging tool) for dependency management,
  virtual environment creation, and build orchestration.
- **Consequences:** Contributors need `uv` installed. Build is faster and more
  reproducible than pip-based workflows.
