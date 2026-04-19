# L24 Handoff Report — Prompt-injection detection + egress auditing

## What shipped

| Section | File(s) | Commit |
|---------|---------|--------|
| §1 — `InjectionScanner` | `src/hestia/security/injection.py`, `src/hestia/security/__init__.py` | (to be committed) |
| §2 — Orchestrator scanner wiring | `src/hestia/orchestrator/engine.py` | (to be committed) |
| §3a — `SecurityConfig` | `src/hestia/config.py` | (to be committed) |
| §3b — Egress table + `record_egress` | `src/hestia/persistence/trace_store.py` | (to be committed) |
| §3c — Egress logging in `http_get` | `src/hestia/tools/builtin/http_get.py` | (to be committed) |
| §3d — Egress logging in `web_search` | `src/hestia/tools/builtin/web_search.py` | (to be committed) |
| §3e — Context variables for trace store | `src/hestia/tools/builtin/memory_tools.py`, `src/hestia/tools/builtin/__init__.py` | (to be committed) |
| §4 — CLI `audit egress` subcommand | `src/hestia/cli.py` | (to be committed) |
| §5a — Unit tests (scanner) | `tests/unit/test_injection_scanner.py` | (to be committed) |
| §5b — Unit tests (orchestrator wiring) | `tests/unit/test_injection_orchestrator.py` | (to be committed) |
| §5c — Integration tests (egress audit) | `tests/integration/test_egress_audit.py` | (to be committed) |
| §6 — README + SECURITY.md | `README.md`, `SECURITY.md` | (to be committed) |
| §7 — ADR-0017 | `docs/adr/ADR-0017-prompt-injection-detection-and-egress-audit.md` | (to be committed) |
| §8 — Version bump | `pyproject.toml`, `CHANGELOG.md` | (to be committed) |
| §9 — Pre-existing mypy fixes | `src/hestia/platforms/matrix_adapter.py`, `src/hestia/platforms/telegram_adapter.py` | (to be committed) |

## Test counts

| Stage | Result |
|-------|--------|
| Baseline (develop) | 573 passed, 6 skipped |
| After L24 commits | 597 passed, 6 skipped |

New tests added:
- `tests/unit/test_injection_scanner.py` — pattern matching, entropy heuristic, false-positive regression on benign content
- `tests/unit/test_injection_orchestrator.py` — scanner integration in `Orchestrator._execute_tool_calls`
- `tests/integration/test_egress_audit.py` — `http_get` and `web_search` egress recording via mocked transport

No test regressions.

## Mypy counts

| Category | Before | After |
|----------|--------|-------|
| Total errors | 2 (pre-existing in adapters) | 0 |

The 2 pre-existing `Future | None` errors in `matrix_adapter.py` and `telegram_adapter.py` were fixed with `assert req.future is not None` guards.

## Blockers / deferred

- None. All sections implemented.

## Post-loop checks

- [x] `uv run pytest tests/unit/ tests/integration/ -q` is green (597 passed, 6 skipped).
- [x] `uv run mypy src/hestia` → 0 errors.
- [x] `pyproject.toml` bumped to 0.5.1.
- [x] `CHANGELOG.md` updated.
- [x] Handoff report written.
