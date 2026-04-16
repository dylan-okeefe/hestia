# Kimi loop L04 — Phase 9 (Matrix test harness + adapter tests)

## Review carry-forward

- **`PytestUnhandledThreadExceptionWarning`** still appears in `tests/unit/test_context_builder.py` (aiosqlite / closed event loop). If L04 touches async tests, consider tightening teardown or xfailing with a tracked issue — not blocking Matrix e2e.
- **L03 CLI refactor** — `CliAppContext` / `hestia matrix` path: smoke-check that `hestia matrix` still boots after Phase 9 wiring; regression risk at orchestrator construction.
- **E2E / Docker** — If §9.1 adds Synapse-backed tests, mark them **skipped** when Docker or compose stack is unavailable so default `pytest tests/unit tests/integration` stays green in environments without Docker; document how to run the full e2e stack in `tests/e2e/README` or handoff.
- **Cron / scheduler** — L03 changed scheduler datetime handling; any new e2e or CLI tests that assert `next_run_at` should use **UTC-aware** or consistently naive times matching store behavior.

**Branch:** `feature/phase-9-test-infra` from latest `develop`.

**Prerequisite:** Matrix adapter (L01) merged — tests assume Matrix transport exists.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§9.1** — Matrix-driven e2e harness, docker-compose, mock llama server, `tests/e2e/` cases listed there.
- **§9.2** — Telegram adapter async tests.
- **§9.3** — CLI integration tests beyond `--help`.

If scope is too large for one run, split commits by subsection but finish all three before writing `.kimi-done`.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` plus any new `tests/e2e/` targets you add — document in handoff if e2e requires Docker locally.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L04-phase-9-test-infra.md
BRANCH=feature/phase-9-test-infra
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
