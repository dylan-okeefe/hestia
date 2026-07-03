# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-07-03

---

## Current task

**Status:** Complete pending Dylan review — migrate `job_alert` subsystem to private repo
**Branch:** `feature/l244-migrate-job-alert-handoff`
**Handoff:** `docs/handoffs/L244-migrate-job-alert-handoff.md`
**TaskView:** Card #26 — "Migrate remaining job-search machinery to private repo (job_alert)"
**Private repo:** `git@github.com-personal:dylan-okeefe/hestia-tools.git` (`~/code/hestia-tools`)

### Summary

Moved the job-alert queue (`JobAlertStore` + `save_job_alert`, `list_pending_alerts`, `mark_alerts_sent`) out of the publishable Hestia core and into the private `hestia-tools` package. The public core no longer contains any job-alert code, table, or registration. The private package uses the L241 `setup(context)` hook to bind a store to Hestia's DB and creates the `job_alerts` table lazily on the first tool call.

### Quality gates

- Hestia `ruff check/format src/hestia/app.py src/hestia/tools/builtin/__init__.py src/hestia/persistence/schema.py`: clean
- Hestia `mypy` on changed files: clean (2 pre-existing errors in `src/hestia/voice/pipeline.py`)
- Hestia `pytest tests/unit/tools/test_external_tool_modules.py tests/unit/tools/test_external_tool_setup.py -q`: 11 passed
- Hestia `pytest tests/unit/tools/ -q`: 110 passed, 15 warnings
- Private repo `pytest tests/ -q` (inside Hestia venv): 13 passed

### Next step

Dylan review of `feature/l244-migrate-job-alert-handoff`; merge to `develop` when approved. Ensure the runtime Hestia config includes `extra_tool_modules=["hestia_tools"]` so the migrated tools are loaded.
