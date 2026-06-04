# Hestia

A personal AI assistant that runs locally. Hestia connects to your chat platforms (Telegram, Matrix), manages scheduled tasks, executes workflows, and provides a web dashboard for administration.

## Features

- **Local inference** — runs on your own hardware via llama.cpp
- **Multi-platform** — Telegram, Matrix, CLI
- **Workflows** — visual workflow editor with triggers and nodes
- **Web dashboard** — admin UI with auth, dark mode, responsive design
- **User registry** — multi-user support with roles and trust levels
- **Memory** — long-term searchable memory with FTS5
- **Scheduler** — cron-based recurring tasks
- **Trust system** — paranoid to developer presets for tool approval

## Quick Start

```bash
pip install hestia
hestia --config config.py serve
```

See [docs/guides/runtime-setup.md](docs/guides/runtime-setup.md) for detailed setup.

## Documentation

- [User Guides](docs/guides/) — setup, platforms, security, voice, email, workflows
- [Architecture Decisions](docs/adr/) — design rationale
- [Changelog](CHANGELOG.md) — version history
- [Release Notes](docs/releases/) — human-facing release summaries

## License

Apache-2.0
