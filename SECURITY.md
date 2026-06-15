# Security

## Supported versions

| Version  | Supported          |
|----------|--------------------|
| 0.13.0   | :white_check_mark: |
| 0.12.x   | :white_check_mark: |
| < 0.12.0 | :x:                |

## Reporting a vulnerability

Please report security issues privately to the maintainers at
[security@example.com](mailto:security@example.com). Include a clear
description of the issue, steps to reproduce, affected versions, and any
suggested fixes or mitigations.

We aim to acknowledge reports within 72 hours and will release patches for
supported versions as quickly as possible. Please do not disclose public
vulnerabilities until a fix is available.

## Config files execute Python

`HestiaConfig.from_file()` loads a Python module via `importlib` and reads a
top-level `config` object (see `src/hestia/config.py`). That means a config
file can execute arbitrary code at import time. This is intentional for
flexibility (shared presets, computed paths, etc.) and is **not** a bug to be
"fixed" by sandboxing in-tree.

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
