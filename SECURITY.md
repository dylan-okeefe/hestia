# Security Policy

## Supported Versions

Hestia is pre-release software. Security fixes land on the `develop` branch and are included in the next tagged release.

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| < 0.7.0 | :x:                |

## Reporting a Vulnerability

Please open a private GitHub Security Advisory at <https://github.com/dylan-okeefe/hestia/security/advisories/new>. Do not open public issues for undisclosed vulnerabilities.

## Security Features

- **Path sandboxing** — file tools are restricted to `storage.allowed_roots`.
- **SSRF protection** — private IP ranges are blocked at connection time.
- **Capability labels** — tools declare capabilities; the policy engine filters by context.
- **Confirmation enforcement** — dangerous tools require explicit user approval.
- **Prompt-injection detection** — tool results are scanned for known patterns and high entropy; hits are annotated, not blocked.
- **Egress auditing** — all outbound HTTP requests are logged for operator review.

## Trust profiles

`TrustConfig` lets operators pick a security posture that matches their deployment. Four presets are built in:

- **`paranoid()`** (default) — Auto-approves nothing. Scheduler and subagents cannot shell or write files. Safest for a fresh install or OSS download.
- **`household()`** — Recommended for single-operator personal deployments. Auto-approves `terminal` and `write_file` on headless platforms; scheduler and subagents can shell and write.
- **`developer()`** — Most permissive. Auto-approves everything. Intended for development/testing only — do not use in a deployment exposed to other users.
- **`prompt_on_mobile()`** — Mobile-confirmation posture. Auto-approves nothing (explicit ✅/❌ prompt on Telegram/Matrix for every dangerous tool), but scheduler and subagents can shell and write.

Tools that declare `requires_confirmation=True` (e.g., `email_send`, `write_file`, `terminal`) trigger a confirmation callback on interactive platforms (CLI). On Telegram and Matrix, the bot sends an inline keyboard or reply pattern. If no confirmation callback is available (e.g., scheduler daemon), the tool is denied unless the trust profile explicitly allows it via `auto_approve_tools`.

## Egress audit

All outbound HTTP requests made by Hestia are logged via `TraceStore`. Operators can review them with:

```bash
hestia audit egress --since 7d
```

This prints a domain-level summary including request counts, failure counts, and anomaly flags (e.g., `LOW_VOLUME` for rarely contacted domains). The audit log is local-only and never leaves the machine.

## Prompt-injection scanner

Hestia includes an entropy-based prompt-injection scanner that runs on all tool results before they enter the model context. When the scanner detects suspicious patterns or unusually high entropy (default threshold: 4.2), it **annotates** the result with a warning rather than blocking it. This avoids false-positive failures while giving the model context that the input may be adversarial.

Tune the threshold in your config:

```python
from hestia.config import HestiaConfig, SecurityConfig

config = HestiaConfig(
    security=SecurityConfig(
        injection_scanner_enabled=True,
        injection_entropy_threshold=4.2,
    ),
)
```

Lower values make the scanner more sensitive; higher values make it more permissive.

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
