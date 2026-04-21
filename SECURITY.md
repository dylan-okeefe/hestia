# Security model

Hestia is designed as a **single-operator**, **local-first** assistant. The
threat model assumes the person who can edit the config file and run the
process is fully trusted.

## Config files execute Python

`HestiaConfig.from_file()` loads a Python module via `importlib` and reads a
top-level `config` object (see `src/hestia/config.py`). That means a config
file can execute arbitrary code at import time. This is intentional for
flexibility (shared presets, computed paths, etc.) and is **not** a bug to be
“fixed” by sandboxing in-tree.

**Operational guidance:** treat `hestia.toml` / `config.py` like shell startup
files: only edit them from accounts you trust, keep them out of world-writable
directories, and never point Hestia at a config file you did not author.

## Credentials

Platform tokens, email passwords, and API keys belong in environment variables
or a restricted `.env` file — never commit them to git. Prefer
`~/.hestia/.env` with `0600` permissions on shared machines.

## Multi-user deployments

When multiple humans share one Hestia instance, use per-platform allow-lists,
per-user trust overrides, and the guides under `docs/guides/multi-user-setup.md`.
Hestia does not provide cryptographic isolation between tenants; operators are
responsible for network and OS-level boundaries.
