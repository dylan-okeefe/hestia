# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-07-03

---

## Current task

**Status:** Complete pending Dylan review — pull job-URL extraction out of workflows/executor.py into a private tool
**Branch:** `feature/l243-extract-job-url-private-tool`
**Handoff:** `docs/handoffs/L243-extract-job-url-private-tool-handoff.md`
**TaskView:** Card #28 — "Pull job-URL extraction out of workflows/executor.py into a private tool"
**Private repo:** `git@github.com-personal:dylan-okeefe/hestia-tools.git` (`~/code/hestia-tools`)

### Summary

Moved the job-board URL extraction logic out of the publishable Hestia workflow executor into the private `hestia-tools` package as the `extract_job_url` tool. The executor now only does generic URL cleanup from LLM output; the stored job-search workflow must be updated to call `extract_job_url` to recover the body-scan fallback.

### Quality gates

- Hestia `mypy src/hestia/workflows/executor.py`: clean
- Hestia `ruff check src/hestia/workflows/executor.py`: clean
- Hestia `pytest tests/unit/tools/ -q`: 110 passed, 15 warnings
- Hestia `pytest tests/unit/workflows/ -q`: blocked by pre-existing `AppContext` fixture config issue (`inference.model_name` empty)
- Private repo `pytest tests/test_job_url_extraction.py -q` (inside Hestia venv): 8 passed

### Next step

Dylan review of `feature/l243-extract-job-url-private-tool`; merge to `develop` when approved. Update the stored job-search workflow to use the new `extract_job_url` tool node.
