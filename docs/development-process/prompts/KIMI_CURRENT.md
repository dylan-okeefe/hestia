# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-07-03

---

## Current task

**Status:** Complete pending Dylan review — external tool module persistence seam
**Branch:** `feature/l241-external-tool-module-setup`
**Handoff:** `docs/handoffs/L241-external-tool-module-setup-handoff.md`
**TaskView:** Card #27 — "Decision: how to get the job_alert subsystem out of the public core"
**Decision:** Option 1 — extend the external-tool-modules seam with a minimal `setup(context)` hook so external modules can own their own persistence. Full external-schema framework deferred until after H2 schema-ownership consolidation.

### Summary

Added `ExternalToolModuleContext` and an optional `setup(context)` hook that runs before `register(registry)` in external tool modules. The context exposes `db` and `config` so a plugin can create its own store (e.g., `JobAlertStore`) without the public core owning that persistence. The job_alert subsystem itself was not migrated yet; this card only builds the seam.

### Quality gates

- `uv run pytest tests/unit/tools/test_external_tool_modules.py tests/unit/tools/test_external_tool_setup.py -q`: **11 passed**
- `uv run mypy` on changed files: **0 errors**
- `uv run ruff check` on changed files: **clean**
- Full-repo gates show only pre-existing issues; no new issues introduced.

### Next step

Dylan review of `feature/l241-external-tool-module-setup`; merge to `develop` when approved. Do not merge without Dylan's okay.
