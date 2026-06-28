# ADR-050: Runtime-introspectable command registry

- **Status:** Accepted
- **Date:** 2026-06-27
- **Context:** Hestia supports slash-commands (`/compact`, `/reset`, `/history`, …) in the CLI REPL, Telegram, and Matrix. Help text was previously hardcoded in `src/hestia/commands/meta.py`, which meant adding or renaming a command required updating help text in multiple places and made drift easy.
- **Decision:** Introduce a lightweight `CommandRegistry` that captures each command's name, aliases, summary, and full help from the handler's docstring at runtime. The registry is populated once in `src/hestia/commands/meta.py` and is reachable from all platform adapters.
- **Consequences:**
  - `/help` and `/commands` are generated from the registry and stay in sync with the actual command surface.
  - A registry lint check (`validate_registry`) fails if any command is missing a docstring-derived summary or long help, preventing drift.
  - Platform adapters (CLI, Telegram, Matrix) resolve commands through the same registry, so behavior is consistent.
  - Tour content and other help-related features can enumerate commands directly from the registry.
