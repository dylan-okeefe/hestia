# L25 Handoff Report — Email adapter (IMAP read + SMTP draft, no auto-send)

## What shipped

| Section | File(s) | Commit |
|---------|---------|--------|
| §1 — `EmailAdapter` | `src/hestia/email/adapter.py`, `src/hestia/email/__init__.py` | 5020fc1 |
| §2 — Email tools | `src/hestia/tools/builtin/email_tools.py` | 5020fc1 |
| §3 — `EmailConfig` | `src/hestia/config.py` | 5020fc1 |
| §4 — TrustConfig gates | `src/hestia/config.py`, `src/hestia/policy/default.py` | 5020fc1 |
| §5a — Integration tests (roundtrip) | `tests/integration/test_email_roundtrip.py` | 5020fc1 |
| §5b — Unit tests (sanitization) | `tests/unit/test_email_sanitization.py` | 5020fc1 |
| §6 — Docs | `docs/guides/email-setup.md`, `README.md` | 5020fc1 |
| §7 — Version bump | `pyproject.toml`, `CHANGELOG.md`, `uv.lock` | 5020fc1 |
| §8 — CLI commands | `src/hestia/cli.py` | 5020fc1 |
| §9 — Capabilities | `src/hestia/tools/capabilities.py`, `src/hestia/tools/builtin/__init__.py` | 5020fc1 |

## Test counts

| Stage | Result |
|-------|--------|
| Baseline (develop) | 597 passed, 6 skipped |
| After L25 commits | 620 passed, 6 skipped |

New tests added:
- `tests/unit/test_email_sanitization.py` — HTML stripping, body truncation, injection scanner interaction, search query parsing, connection error handling
- `tests/integration/test_email_roundtrip.py` — draft → list → send via mocked IMAP/SMTP, search/flag/move workflows, tool factory verification

No test regressions.

## Mypy counts

| Category | Before | After |
|----------|--------|-------|
| Total errors | 0 | 0 |

## Ruff counts

No new lint debt introduced in changed files. Pre-existing issues in `cli.py`, `policy/default.py`, and other files were not touched.

## Blockers / deferred

- None. All sections implemented.

## Post-loop checks

- [x] `uv run pytest tests/unit/ tests/integration/ -q` is green (620 passed, 6 skipped).
- [x] `uv run mypy src/hestia` → 0 errors.
- [x] `pyproject.toml` bumped to 0.6.0.
- [x] `CHANGELOG.md` updated.
- [x] `uv.lock` updated.
- [x] `docs/guides/email-setup.md` written and linked from README.
- [x] Handoff report written.
- [x] Feature branch `feature/l25-email-adapter` pushed.
