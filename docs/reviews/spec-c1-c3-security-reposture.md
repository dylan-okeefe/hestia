# Spec: C1/C3 security re-posture

## Scope
Add startup guards that prevent the Hestia web dashboard from running in an
accidentally insecure configuration, plus the supporting config/example changes.

See `decisions-c1-c3-security-reposture.md` for the rationale and trade-offs.

## Requirements

### C1: Authentication loopback guard
When `web.enabled` is True and `web.auth_enabled` is False:

- If `web.host` is loopback, startup proceeds.
- If `web.host` is exposed and `web.allow_insecure` is False, startup aborts.
- If `web.host` is exposed and `web.allow_insecure` is True, startup proceeds.

### C3: Auto-approve wildcard/destructive guard
When `web.host` is exposed and `trust.auto_approve_tools` contains `"*"` or any
of `terminal`, `write_file`, `email_send`:

- If `web.auth_enabled` is False and `web.allow_insecure` is False, startup
  aborts.
- If `web.auth_enabled` is True, log a warning and proceed.
- If `web.allow_insecure` is True, bypass the guard.

### Loopback definition
Implemented by `is_loopback_host()` in `src/hestia/web/auth.py`:

- `localhost` is loopback.
- 127.0.0.0/8 is loopback.
- ::1 is loopback.
- Everything else (including `0.0.0.0` and LAN IPs) is exposed.

### Config schema
`WebConfig` gains `allow_insecure: bool = False` (env `HESTIA_WEB_ALLOW_INSECURE`).

### Example config
`config.runtime.example.py` demonstrates the safe posture:

- `web.host = "127.0.0.1"`
- `web.auth_enabled = True`
- `web.allow_insecure = False`
- `trust = TrustConfig.household()`

### Personal config untracked
`config.runtime.py` is removed from git tracking and added to `.gitignore`.

## Implementation map

| Requirement | File |
|-------------|------|
| `allow_insecure` flag | `src/hestia/config.py` |
| `is_loopback_host()` | `src/hestia/web/auth.py` |
| C1/C3 guards | `src/hestia/app.py` (`_validate_web_security_posture`) |
| Untrack personal config | `config.runtime.py`, `.gitignore` |
| Example safe config | `config.runtime.example.py` |
| Decision record | `docs/reviews/decisions-c1-c3-security-reposture.md` |
| Tests | `tests/unit/test_config.py`, `tests/unit/test_web_auth.py` |

## Acceptance
- `pytest tests/unit/test_config.py tests/unit/test_web_auth.py -q` passes.
- `ruff check` and `mypy` are clean on changed Python files.
- `git ls-files | grep config.runtime.py` returns only `config.runtime.example.py`.
