# L27 Handoff Report — Interaction-style profile system

## What shipped

| Section | File(s) | Commit |
|---------|---------|--------|
| §1 — Style metrics store | `src/hestia/style/store.py`, `src/hestia/persistence/schema.py` | 8280198 |
| §2 — `StyleProfileBuilder` | `src/hestia/style/builder.py`, `src/hestia/style/vocab.py` | 8280198 |
| §3 — Context-builder integration | `src/hestia/context/builder.py` | 8280198 |
| §4 — CLI surface | `src/hestia/cli.py` | 8280198 |
| §5 — `StyleConfig` | `src/hestia/config.py` | 8280198 |
| §6a — Unit tests (builder) | `tests/unit/test_style_builder.py` | 8280198 |
| §6b — Unit tests (context) | `tests/unit/test_style_profile_context.py` | 8280198 |
| §6c — Integration tests (lifecycle) | `tests/integration/test_style_lifecycle.py` | 8280198 |
| §7a — README update | `README.md` | 8280198 |
| §7b — ADR | `docs/adr/ADR-019-style-profile-vs-identity.md` | 8280198 |
| §8 — Scheduler integration | `src/hestia/style/scheduler.py`, `src/hestia/cli.py` | 8280198 |
| §9 — Orchestrator wiring | `src/hestia/orchestrator/engine.py` | 8280198 |
| §10 — Version bump | `pyproject.toml`, `CHANGELOG.md`, `uv.lock` | 8280198 |

## Test counts

| Stage | Result |
|-------|--------|
| Baseline (develop) | 643 passed, 12 skipped |
| After L27 commits | 658 passed, 12 skipped |

New tests added:
- `tests/unit/test_style_builder.py` — preferred_length (feedback exclusion, median, no traces), formality (casual, technical), top_topics (empty), activity_window (histogram)
- `tests/unit/test_style_profile_context.py` — ordering (style last), omission when None, setter
- `tests/integration/test_style_lifecycle.py` — scheduler tick builds profile, context injection, CLI reset, cold start no prefix, namespaced per user

No test regressions. One pre-existing smoke test failure (`tests/smoke/test_phase_1b_integration.py::test_proto_orchestrator_uses_terminal_tool`) unrelated to this loop.

## Mypy counts

| Category | Before | After |
|----------|--------|-------|
| Total errors | 0 | 0 |

## Ruff counts

No new lint debt introduced in changed files.

## Blockers / deferred

- None. All sections implemented.
- Formality heuristic is a static word list (~300 terms). A future loop could replace this with a lightweight classifier if needed.
- Preferred length uses median completion tokens, which is a proxy. A future loop could use explicit user feedback signals if we add thumbs-up/down.

## Post-loop checks

- [x] `uv run pytest tests/unit/ tests/integration/ -q` is green (658 passed, 12 skipped).
- [x] `uv run mypy src/hestia` → 0 errors.
- [x] `pyproject.toml` bumped to 0.7.1.
- [x] `CHANGELOG.md` updated.
- [x] `README.md` updated with "Style profile" subsection under "Reflection loop".
- [x] ADR-019 written.
- [x] Handoff report written.
- [x] Feature branch `feature/l27-style-profile` pushed.
