# Security Policy

## Supported Versions

Hestia is pre-release software. Security fixes land on the `develop` branch and are included in the next tagged release.

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | :white_check_mark: |
| < 0.5.0 | :x:                |

## Reporting a Vulnerability

Please report security issues directly to the maintainer via email (see the repository owner's profile). Do not open public issues for undisclosed vulnerabilities.

## Security Features

- **Path sandboxing** — file tools are restricted to `storage.allowed_roots`.
- **SSRF protection** — private IP ranges are blocked at connection time.
- **Capability labels** — tools declare capabilities; the policy engine filters by context.
- **Confirmation enforcement** — dangerous tools require explicit user approval.
- **Prompt-injection detection** — tool results are scanned for known patterns and high entropy; hits are annotated, not blocked.
- **Egress auditing** — all outbound HTTP requests are logged for operator review.

## Configuration

Security toggles live in `SecurityConfig` (wired as `HestiaConfig.security`):

```python
from hestia.config import HestiaConfig, SecurityConfig

config = HestiaConfig(
    security=SecurityConfig(
        injection_scanner_enabled=True,
        injection_entropy_threshold=4.2,
        egress_audit_enabled=True,
    ),
)
```
