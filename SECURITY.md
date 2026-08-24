# Security

## Supported versions

Hestia is a solo-maintained, local-first project. Security fixes land on
the current development branch (`develop`) and are released with the
current stable minor series (`0.16.x` at the time of writing). Older
versions do not receive backports; if you are running one, upgrade.

## Reporting a vulnerability

Please report security issues privately through
[GitHub private vulnerability reporting](https://github.com/dylan-okeefe/hestia/security/advisories/new):
open the repository's **Security** tab and use **Report a vulnerability**.
Do not open a public issue for anything you believe is exploitable.

Include a clear description of the issue, steps to reproduce, affected
versions, and any suggested fixes or mitigations.

We aim to acknowledge reports within 72 hours and will release patches for
supported versions as quickly as possible. Please do not disclose publicly
until a fix is available.

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
