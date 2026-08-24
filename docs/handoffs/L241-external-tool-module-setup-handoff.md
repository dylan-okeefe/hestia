# L241 — External Tool Module Persistence Seam (`setup(context)`)

**Branch:** `feature/l241-external-tool-module-setup`
**Status:** Implementation complete; ready for review.
**TaskView:** Card #27 — "Decision: how to get the job_alert subsystem out of the public core"
**Decision:** Option 1 — extend the external-tool-modules seam with a minimal `setup(context)` hook so external modules can own their own persistence. Full external-schema framework deferred until after H2 schema-ownership consolidation.

## What changed

- Added `src/hestia/tools/external_context.py` with `ExternalToolModuleContext`.
  - Narrow context object exposing `db: Database` and `config: HestiaConfig`.
  - Explicitly does not pass the full `AppContext` to limit the trust surface.
- Updated `src/hestia/app.py`:
  - `_register_external_tool_modules()` now calls optional `setup(context)` before `register(registry)`.
  - Any exception from `setup` is logged as a warning and skips that module entirely (its `register` is not called).
  - Missing `setup` preserves L240 backward compatibility for pure-tool modules.
- Re-exported `ExternalToolModuleContext` from `src/hestia/tools/__init__.py`.
- Added fixture modules:
  - `tests/fixtures/external_tool_module/setup_tools.py` — uses `setup` to create a store, then registers tools that read from it.
  - `tests/fixtures/external_tool_module/setup_fails.py` — deliberately raises in `setup` to test skip behavior.
- Added `tests/unit/tools/test_external_tool_setup.py` covering:
  - `setup` runs before `register`.
  - `setup` failure logs a warning and skips registration.
  - Missing `setup` still allows `register` (backward compat).
  - Context exposes `db` and `config`.
  - Tools registered after setup are still capability-filtered for subagent sessions.
- Updated `docs/adr/ADR-053-external-tool-modules.md` to document the optional `setup(context)` hook and the database-handle trust warning.
- Updated `docs/guides/custom-tools.md` with a `setup(context)` example and a trust warning about `context.db`.

## What did NOT change

- `job_alert_store.py`, `job_alert_tools.py`, and their registration in `app.py` remain in place.
  - The actual migration of the job_alert subsystem to a private repo is blocked on having the private repo and is intentionally left for a follow-up loop.

## Commits

- `c89d42a0` — feat: add ExternalToolModuleContext and setup hook for external tool modules
- `efd3c6b2` — test: external tool module setup hook behavior
- `42515d7b` — docs: update ADR and guide for external module setup hook

## Quality gates

- `uv run pytest tests/unit/tools/test_external_tool_modules.py tests/unit/tools/test_external_tool_setup.py -q`: **11 passed**
- `uv run mypy src/hestia/app.py src/hestia/tools/external_context.py tests/unit/tools/test_external_tool_setup.py tests/fixtures/external_tool_module/`: **0 errors**
- `uv run ruff check` on changed files: **clean**
- Full-repo gates still show only pre-existing issues; no new issues introduced.

## Notes for next step

- Dylan/Cursor review and merge to `develop` when approved.
- Once merged, the private repo can implement `setup(context)` to create a `JobAlertStore(context.db)`, then register the job-alert tools. At that point the public core can remove `job_alert_store`, `job_alert_tools.py`, and their `app.py` registration.
- No merge or push was performed yet.
