# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-07-03

---

## Current task

**Status:** Complete pending Dylan review — external tool modules extension point
**Branch:** `feature/l240-external-tool-modules`
**Handoff:** `docs/handoffs/L240-external-tool-modules-handoff.md`
**ADR:** `docs/adr/ADR-051-external-tool-modules.md`
**TaskView:** Card #25 — "External tool modules (custom-tool extension point)"

### Summary

Implemented an opt-in seam that lets external Python packages contribute `@tool` callables via a `register(registry)` hook, loaded from the new `extra_tool_modules` config field. External tools are registered in the same `ToolRegistry` as built-ins and remain fully subject to `CapabilityGate` and `DefaultPolicyEngine` filtering.

### Quality gates

- `uv run pytest tests/unit/tools/test_external_tool_modules.py -q`: **6 passed**
- `uv run pytest tests/unit/tools/ tests/unit/policy/ tests/unit/test_config.py tests/unit/test_config_env.py -q`: **179 passed**
- `uv run mypy` on changed files: **0 errors**
- `uv run ruff check` on changed files: **clean**
- Full-repo gates show only pre-existing issues; no new issues introduced.

### Next step

Dylan review of `feature/l240-external-tool-modules`; merge to `develop` when approved. Do not merge without Dylan's okay.
