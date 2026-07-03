# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-07-03

---

## Current task

**Status:** Complete pending Dylan review — migrate `indeed_search_jobs` to private repo
**Branch:** `feature/l242-private-tool-migration`
**Handoff:** `docs/handoffs/L242-migrate-indeed-search-handoff.md`
**Private repo:** `git@github.com-personal:dylan-okeefe/hestia-tools.git` (`~/code/hestia-tools`)

### Summary

Migrated `indeed_search_jobs` out of the publishable Hestia core into the private `hestia-tools` package. Made `http_get_impl` public so external modules can reuse Hestia's SSRF-guarded fetch path. The private repo is installed in Hestia's environment and loaded via `extra_tool_modules=["hestia_tools"]`.

### Quality gates

- Hestia external-tool tests: **11 passed**
- Hestia unit/tools: **110 passed, 15 warnings**
- `mypy` / `ruff` on changed Hestia files: clean
- Private repo test (run inside Hestia venv): **1 passed**

### Next step

Dylan review of `feature/l242-migrate-indeed-search`; merge to `develop` when approved. Do not merge without Dylan's okay.
