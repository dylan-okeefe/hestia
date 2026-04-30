# L63 — Security Defaults & Trust Hardening Handoff

**Branch:** `feature/l63-security-defaults-and-trust-hardening`
**Status:** Complete, ready for review

## Changes

### §1 — `allowed_roots` default-deny
- `StorageConfig.allowed_roots` default changed from `["."]` to `[]`
- `_check_allowed_roots_cwd` in `doctor.py` now warns when empty, telling users filesystem tools are disabled

### §2 — EmailConfig password repr redaction
- Added `__repr__` to `EmailConfig` that masks `password` and `resolved_password` fields

### §2a — TelegramConfig bot_token repr redaction
- Added `__repr__` to `TelegramConfig` that masks `bot_token` field

### §3 — hestia doctor warns on developer preset
- Added `_check_trust_preset_safe_for_production` doctor check
- Fails when `trust.preset == "developer"` and `HESTIA_ENV` is not `"development"`

### §4 — TrustConfig.developer() warning
- Added `logger.warning()` when `developer()` preset is instantiated
- Expanded docstring to explain the danger

## Quality gates

- `pytest tests/unit/test_path_sandboxing.py` — 5 passed
- `pytest tests/unit/test_config.py` — 30 passed
- `mypy src/hestia/config.py src/hestia/doctor.py` — no issues
- `ruff check src/hestia/config.py src/hestia/doctor.py` — clean

## Intent verification

- **Safe by default:** A fresh config with no `allowed_roots` set will deny all filesystem access. `check_path_allowed` already handles empty lists correctly.
- **Credential redaction:** `repr()` of both config classes now shows `***` for sensitive fields.
- **Developer preset is frictionful:** `doctor` fails loudly, and logs warn at construction time.

## Next

Ready to merge to `develop` and start L64.
