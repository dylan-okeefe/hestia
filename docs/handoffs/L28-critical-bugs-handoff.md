# L28 Handoff Report — Critical correctness bugs + dependency hygiene

## What shipped

| Section | File(s) | Commit |
|---------|---------|--------|
| §1 — Replace `bleach` with `nh3` | `pyproject.toml`, `src/hestia/email/adapter.py`, `uv.lock` | 063bf2f |
| §2a — Register `read_artifact` | `src/hestia/cli.py`, `src/hestia/tools/builtin/__init__.py` | a65180b |
| §2b — Add `delete_memory` tool | `src/hestia/tools/builtin/memory_tools.py`, `src/hestia/cli.py` | a65180b |
| §3 — Fix `create_draft` Message-ID | `src/hestia/email/adapter.py` | 634f64a |
| §4 — Harden `_parse_search_query` | `src/hestia/email/adapter.py` | 2c59ed5 |
| §5 — Drop dead `get_profile_dict` stub | `src/hestia/style/builder.py` | ca86f5b |
| §6 — Version bump + CHANGELOG | `pyproject.toml`, `CHANGELOG.md`, `uv.lock` | 045b9c1 |
| §1 tests | `tests/unit/test_email_adapter_html_sanitize.py` | 063bf2f |
| §2 tests | `tests/unit/test_read_artifact_registered.py`, `tests/unit/test_delete_memory_tool.py`, `tests/integration/test_cli_tools_registered.py` | a65180b |
| §3 tests | `tests/unit/test_email_create_draft.py` | 634f64a |
| §4 tests | `tests/unit/test_email_search_parser.py` | 2c59ed5 |
| §5 tests | `tests/unit/test_style_builder_no_dead_method.py` | ca86f5b |

## Test counts

| Stage | Result |
|-------|--------|
| Baseline (develop) | 652 passed, 6 skipped |
| After L28 commits | 673 passed, 6 skipped |

New tests added:
- `tests/unit/test_email_adapter_html_sanitize.py` — sanitize strips script, disabled passthrough, empty string
- `tests/unit/test_read_artifact_registered.py` — read_artifact and delete_memory registered in registry
- `tests/unit/test_delete_memory_tool.py` — delete existing, delete unknown, tool metadata
- `tests/integration/test_cli_tools_registered.py` — registry contains both tools via CLI bootstrap
- `tests/unit/test_email_create_draft.py` — Message-ID in appended bytes, real UID returned, raises on miss, rejects draft-unknown
- `tests/unit/test_email_search_parser.py` — FROM, SUBJECT, SINCE, quote escaping, injection attempt, malformed SINCE raises, default subject
- `tests/unit/test_style_builder_no_dead_method.py` — assert dead method removed

No test regressions.

## Mypy counts

| Category | Before | After |
|----------|--------|-------|
| Total errors | 0 | 0 |

## Ruff counts

No new lint debt introduced in changed files. Pre-existing `cli.py` lint (E501, SIM108, etc.) was not touched per loop rules.

## Blockers / deferred

- None. All seven bugs fixed with regression tests.

## Post-loop checklist

- [x] `uv run pytest tests/unit/ tests/integration/ -q` is green (673 passed, 6 skipped).
- [x] `uv run mypy src/hestia` → 0 errors.
- [x] `pyproject.toml` bumped to 0.7.2.
- [x] `CHANGELOG.md` updated.
- [x] `uv.lock` synced in same commit as version bump.
- [x] Handoff report written.
- [x] Feature branch `feature/l28-critical-bugs` ready for push.
