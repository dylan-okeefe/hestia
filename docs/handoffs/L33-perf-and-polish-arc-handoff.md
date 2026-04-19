# L33 Perf and Polish Arc — Handoff

## Scope

This handoff covers the three mini-loops that refined security tuning, email performance, and skills framework visibility:

- **L33a** — `InjectionScanner` threshold tuning + structured-content filters (v0.7.9)
- **L33b** — `EmailAdapter` per-invocation IMAP session reuse + `email_search_and_read` composite tool (v0.7.10)
- **L33c** — Skills experimental feature flag + minor polish (v0.7.11)

## Specs

- `docs/development-process/kimi-loops/L33a-injection-scanner-tuning.md`
- `docs/development-process/kimi-loops/L33b-email-session-reuse.md`
- `docs/development-process/kimi-loops/L33c-skills-flag-and-polish.md`

## Files changed

| Loop | File | Change |
|------|------|--------|
| L33a | `src/hestia/security/injection.py` | Raised default `entropy_threshold` to 5.5; added structured-content skip (JSON, base64, CSS) |
| L33a | `src/hestia/config.py` | Added `injection_entropy_threshold` and `injection_skip_filters_for_structured` to `SecurityConfig` |
| L33a | `tests/unit/test_injection_scanner_tuning.py` | Regression coverage for threshold and structured-content filters |
| L33b | `src/hestia/email/adapter.py` | Added `imap_session()` async context manager with `ContextVar`-based connection reuse |
| L33b | `src/hestia/tools/builtin/email_tools.py` | Routed all IMAP methods through `imap_session()`; added `email_search_and_read` composite tool |
| L33b | `tests/unit/test_email_session_reuse.py` | Single-connection reuse, cleanup on exception, nested-session deduplication |
| L33b | `tests/integration/test_email_search_and_read.py` | End-to-end composite tool coverage |
| L33c | `src/hestia/errors.py` | Added `ExperimentalFeatureError` |
| L33c | `src/hestia/skills/decorator.py` | `@skill` raises `ExperimentalFeatureError` without `HESTIA_EXPERIMENTAL_SKILLS=1` |
| L33c | `src/hestia/cli.py` | `hestia skill *` commands exit with error when flag is unset |
| L33c | `src/hestia/policy/default.py` | Added `DEFAULT_DELEGATION_KEYWORDS`; `should_delegate` reads from `PolicyConfig.delegation_keywords` |
| L33c | `src/hestia/config.py` | Added `PolicyConfig` dataclass with `delegation_keywords` |
| L33c | `src/hestia/app.py` | Hoisted `_format_datetime` to module scope; wired `PolicyConfig` through `_make_policy` |
| L33c | `README.md` | Renamed skills heading to "Skills (experimental preview)" with env-var callout |
| L33c | `docs/adr/ADR-0022-skills-preview-feature-flag.md` | ADR documenting the gate and rejection of silent no-op |
| L33c | `tests/unit/test_skills_feature_flag.py` | Flag gate regression coverage |
| L33c | `tests/unit/test_policy_delegation_keywords.py` | Custom and empty keyword config coverage |
| L33c | `tests/unit/test_matrix_adapter.py` | `_extract_in_reply_to` schema validation contract tests |

## User-visible behavior changes

1. **Injection scanner is less noisy** (L33a). Real tool outputs (JSON, base64, CSS) no longer false-positive on entropy. Operators can tune via `SecurityConfig.injection_entropy_threshold`.
2. **Email IMAP operations are faster** (L33b). Nested `email_list` + `email_read` calls inside `async with adapter.imap_session():` reuse a single TLS connection. Standalone calls remain backward-compatible.
3. **Skills framework requires explicit opt-in** (L33c). `HESTIA_EXPERIMENTAL_SKILLS=1` must be set before `@skill` or `hestia skill *` will function. Prevents silent no-op confusion.
4. **Delegation keywords are tunable** (L33c). Operators can override `PolicyConfig.delegation_keywords` or set `()` to disable keyword-based delegation entirely.

## Final gate

```
Tests:    741 passed, 6 skipped
Mypy:     0 errors
Ruff:     44 errors (no regression)
Version:  0.7.11
Branch:   feature/l33c-skills-flag-and-polish
```

## Design notes for future loops

- The skills feature flag should be removed once the orchestrator wires `run_skill` into the turn loop. The env-var gate is a temporary visibility measure, not a long-term security boundary.
- `PolicyConfig.delegation_keywords` uses a tuple to stay immutable/hashable. If future loops want regex or semantic matching, a new config field (`delegation_patterns`, etc.) should be added alongside it.
- `_format_datetime` is now at module scope but still only consumed by schedule-show. If other commands need it, no further hoist is required.
