# Kimi loop L07 — Phase 12 (manual skills)

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
