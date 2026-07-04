# Decisions: C1/C3 security re-posture

## Context
The Hestia web dashboard currently defaults to `127.0.0.1:8765` with auth
enabled, but nothing stops a user from disabling auth or binding to an exposed
interface. The `TrustConfig.developer()` preset uses `auto_approve_tools=["*"]`,
which lets anyone who can reach the dashboard invoke destructive tools without
confirmation. We need guards that prevent accidental insecure deployments
without breaking Dylan's existing runtime.

## Decisions

### 1. What counts as loopback?
Only the following are treated as loopback-only:

- The literal string `localhost` (case-insensitive).
- IPv4 addresses in 127.0.0.0/8.
- The IPv6 address ::1.

LAN IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, etc.), `0.0.0.0`, empty
strings, and hostnames are treated as exposed.

### 2. Single escape hatch
One flag controls both the C1 and C3 guards:

- Config: `web.allow_insecure = False` (env: `HESTIA_WEB_ALLOW_INSECURE=1`).

When `allow_insecure` is True, the startup guards are bypassed. This is
intended for isolated development environments only.

### 3. C1 guard: auth disabled on exposed interface
If `web.enabled` is True, `web.auth_enabled` is False, `web.host` is not
loopback, and `web.allow_insecure` is False, startup aborts with
`HestiaConfigError`.

### 4. C3 guard: wildcard/destructive auto-approve on exposed interface
If `web.host` is exposed and `trust.auto_approve_tools` contains `"*"` or any
destructive tool (`terminal`, `write_file`, `email_send`):

- With auth disabled (and `allow_insecure` False): startup aborts.
- With auth enabled: a warning is logged every boot. The warning is not
  suppressible beyond setting `allow_insecure=True`.

This preserves Dylan's runtime configuration (auth on, `0.0.0.0`, developer
preset with wildcard) while making the risk visible.

### 5. Default posture for example config
`config.runtime.example.py` uses:

- `web.host = "127.0.0.1"`
- `web.auth_enabled = True`
- `web.allow_insecure = False`
- `trust = TrustConfig.household()` (no wildcard)

### 6. Untrack personal runtime config
`config.runtime.py` is removed from git tracking and added to `.gitignore`.
Fresh clones must copy `config.runtime.example.py` to `config.runtime.py`. The
runtime worktree's existing copy is unaffected.

## Consequences
- A fresh public clone no longer ships a personal config file.
- Users who disable auth and bind to `0.0.0.0` must explicitly opt in via
  `allow_insecure`.
- Dylan's runtime keeps working but sees a warning on each boot.
