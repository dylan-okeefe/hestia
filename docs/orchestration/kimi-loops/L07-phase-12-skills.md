# Kimi loop L07 — Phase 12 (manual skills)

## Review carry-forward

- **Test baseline:** **`386 passed`** after L06 — keep unit/integration green.
- **`CliAppContext`** — L03/L06 extended context (`trace_store`, etc.); wire any new stores for skills through the same pattern (`make_orchestrator` / bootstrap).
- **Traces + failures** — `FailureBundle.trace_id` exists; optional linkage when a skill run goes through `process_turn` (don’t block skills on traces if insert fails).
- **Migrations** — L06 added `traces` + `failure_bundles` columns; stack new `skills` migration **after** latest head.

**Branch:** `feature/phase-12-skills` from latest `develop`.

**Implement** from [`../../design/hestia-phase-8-plus-roadmap.md`](../../design/hestia-phase-8-plus-roadmap.md):

- **§12.1–§12.5** — Skill lifecycle, definition format, prompt index, persistence, CLI commands, **ADR-024**.

---

## Completion

1. `uv run pytest tests/unit/ tests/integration/ -q` — green.
2. Commit and `git push`.
3. Write **`.kimi-done`**:

```text
HESTIA_KIMI_DONE=1
SPEC=docs/orchestration/kimi-loops/L07-phase-12-skills.md
BRANCH=feature/phase-12-skills
PYTEST=<last line of pytest -q>
GIT_HEAD=<git rev-parse HEAD>
```

4. Do **not** commit `.kimi-done`.
