# Kimi loop L03 — Phase 8b (CLI context, exceptions, datetime)

**Branch:** `feature/phase-8b-cli-exceptions-datetime` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§8.3** — `CliAppContext` dataclass, `make_orchestrator()`, refactor `cli.py` (no behavior change).
- **§8.4** — Narrow bare `except Exception` catches per the table in the roadmap.
- **§8.5** — `core/clock.py`, replace naive `datetime.now()` usage, scheduler/CLI display boundaries, tests as specified.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L03-phase-8b-cli-exceptions-datetime.md
BRANCH=feature/phase-8b-cli-exceptions-datetime
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
