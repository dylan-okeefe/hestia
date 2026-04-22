# ADR-028: HestiaConfig is a typed Python dataclass loaded from a Python file

- **Status:** Accepted
- **Date:** 2026-04-10
- **Context:** Configuration was scattered across Click CLI options and
  constructor arguments in cli.py. Adding platform adapters (Telegram,
  Matrix) would require passing many new options through the CLI, making
  the interface unwieldy and hard to validate.

- **Decision:**
  1. Introduce `HestiaConfig` as a top-level dataclass with sub-configs
     for inference, slots, scheduler, and storage. Config files are
     Python files that define a `config` variable, loaded via
     `importlib`.
  2. CLI options override config values when explicitly provided. If no
     config file is given, sensible defaults apply.
  3. Config is type-checked at load time (it's a Python import, not a
     YAML parse). IDE autocompletion works on the config file.

- **Consequences:**
  - Platform adapters (Phase 3+) can add their own config sub-objects
    (TelegramConfig, MatrixConfig) without growing the CLI option list.
  - Config files are version-controllable, diffable, and self-documenting.
  - Users who don't want a config file can use CLI options exclusively
    and get the same behavior as today.
  - The tradeoff vs. TOML/YAML is that config files are executable code.
    This is acceptable for a single-user local tool; it would not be
    acceptable for a multi-tenant service.
