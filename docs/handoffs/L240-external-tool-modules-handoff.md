# L240 — External Tool Modules (Custom-Tool Extension Point)

**Branch:** `feature/l240-external-tool-modules`
**Status:** Implementation complete; ready for review.
**TaskView:** Card #25 — "External tool modules (custom-tool extension point)"

## What changed

- Added `extra_tool_modules: list[str]` to `HestiaConfig` in `src/hestia/config.py`.
  - Empty default; dotted Python import paths; loaded from `HESTIA_EXTRA_TOOL_MODULES` env var as a JSON list.
- Wired external module loading in `src/hestia/app.py`.
  - New `_register_external_tool_modules()` is called at the end of `AppContext.register_tools()` after all built-ins.
  - Imports each configured module and calls `register(registry)` if present.
  - Logs a warning and skips on import error, missing/non-callable `register`, or `ValueError` from registration (e.g., duplicate tool name).
- Added fixture package `tests/fixtures/external_tool_module/` with example tools.
- Added `tests/unit/tools/test_external_tool_modules.py` covering:
  - External tool loads and is callable.
  - Missing `register` hook logs a warning and skips.
  - Import error logs a warning and does not crash.
  - External `SHELL_EXEC` tool is filtered out for subagent sessions (no trust bypass).
  - Empty `extra_tool_modules` leaves built-in registration unchanged.
  - Config field loads from `HESTIA_EXTRA_TOOL_MODULES` env var.
- Added `docs/adr/ADR-053-external-tool-modules.md` documenting the opt-in, explicit-register, no-autoload, full-trust-boundary decisions.
- Added "External tool modules" section to `docs/guides/custom-tools.md` with setup steps and a trust warning.

## Commits

- `5e7a5a28` — feat: add extra_tool_modules config field
- `edc10c03` — feat: wire external tool module registration in AppContext
- `4a42a80b` — test: external tool module loading and capability gating
- `0061d9fe` — docs: ADR and guide for external tool modules

## Quality gates

- `uv run pytest tests/unit/tools/test_external_tool_modules.py -q`: **6 passed**
- `uv run pytest tests/unit/tools/ tests/unit/policy/ tests/unit/test_config.py tests/unit/test_config_env.py -q`: **179 passed**
- `uv run mypy src/hestia/config.py src/hestia/app.py tests/unit/tools/test_external_tool_modules.py tests/fixtures/external_tool_module/`: **0 errors**
- `uv run ruff check src/hestia/config.py src/hestia/app.py tests/unit/tools/test_external_tool_modules.py tests/fixtures/external_tool_module/`: **clean**
- Full-repo `uv run mypy src/hestia` reports **2 pre-existing errors** in `src/hestia/tools/builtin/indeed_search.py`; no new errors introduced.
- Full-repo `uv run ruff check src/ tests/` reports pre-existing issues in unrelated files; no new issues introduced by this branch.
- Full `uv run pytest tests/unit/ tests/integration/ -q` times out at 300s and contains pre-existing failures unrelated to this change.

## Notes for next step

- Dylan/Cursor review and merge to `develop` when approved.
- This unblocks migrating the job-search scrapers from the do-not-merge `feature/job-search-tools` branch to a private repo loaded via `extra_tool_modules`.
- No merge or push was performed per instructions.
