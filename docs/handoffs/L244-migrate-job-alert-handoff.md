# L244 — Migrate `job_alert` subsystem to Private Repo

**Branch:** `feature/l244-migrate-job-alert-handoff`
**Status:** Implementation complete; ready for review.
**Private repo:** `git@github.com-personal:dylan-okeefe/hestia-tools.git` (`~/code/hestia-tools`)

## What changed

### Public Hestia core

- Removed `src/hestia/persistence/job_alert_store.py`.
- Removed `src/hestia/tools/builtin/job_alert_tools.py`.
- Removed the `job_alerts` table definition from `src/hestia/persistence/schema.py`.
- Updated `src/hestia/tools/builtin/__init__.py` to drop imports and `__all__` entries for `make_save_job_alert_tool`, `make_list_pending_alerts_tool`, and `make_mark_alerts_sent_tool`.
- Updated `src/hestia/app.py`:
  - Removed `JobAlertStore` import.
  - Removed the three job-alert tool imports from `hestia.tools.builtin`.
  - Removed `self.job_alert_store = JobAlertStore(self.db)`.
  - Removed `await self.job_alert_store.create_table()`.
  - Removed the three `reg.register(make_*_tool(...))` calls.
- Regenerated `metrics.json`.

### Private `hestia-tools` repo

- Added `hestia_tools/job_alert_store.py` with `JobAlertStore` and a local `job_alerts` SQLAlchemy Core table (same name, columns, and indexes as the Hestia table for data compatibility).
- Added `hestia_tools/job_alert_tools.py` with `save_job_alert`, `list_pending_alerts`, and `mark_alerts_sent` tools.
- Updated `hestia_tools/__init__.py`:
  - Added `setup(context)` that binds `JobAlertStore(context.db)` module-globally.
  - Registered the three job-alert tools in `register(registry)`.
- Added `tests/test_job_alert_tools.py` covering tool registration and save/list/mark-sent round-trip.
- Updated `README.md` to document the new tools.

## Approach

Used the existing L241 external-tool-module seam without modifying Hestia. Because `setup(context)` is synchronous and table creation is async, the private package lazily creates the `job_alerts` table on the first async tool call. A module-level `_table_ensured` flag is used only as a fast-path; `checkfirst=True` is the real guard, so concurrent first calls are harmless.

## Commits

Public Hestia core (`feature/l244-migrate-job-alert-handoff`):
- TBD — refactor: remove job_alert subsystem from public core
- TBD — chore: update metrics.json after L244

Private `hestia-tools` repo (`main`):
- `687754a` — feat: migrate job_alert store and tools from Hestia public core

## Quality gates

Hestia:
- `PYTHONPATH=/home/dylan/Hestia/src ruff check src/hestia/app.py src/hestia/tools/builtin/__init__.py src/hestia/persistence/schema.py`: **clean**
- `PYTHONPATH=/home/dylan/Hestia/src ruff format --check src/hestia/app.py src/hestia/tools/builtin/__init__.py src/hestia/persistence/schema.py`: **clean**
- `PYTHONPATH=/home/dylan/Hestia/src mypy src/hestia/app.py src/hestia/tools/builtin/__init__.py src/hestia/persistence/schema.py`: **0 errors in changed files** (2 pre-existing errors in `src/hestia/voice/pipeline.py`)
- `PYTHONPATH=/home/dylan/Hestia/src pytest tests/unit/tools/test_external_tool_modules.py tests/unit/tools/test_external_tool_setup.py -q`: **11 passed**
- `PYTHONPATH=/home/dylan/Hestia/src pytest tests/unit/tools/ -q`: **110 passed, 15 warnings**

Private repo (installed in Hestia venv):
- `PYTHONPATH=/home/dylan/Hestia/src:/home/dylan/code/hestia-tools pytest /home/dylan/code/hestia-tools/tests/test_job_alert_tools.py -q`: **4 passed**
- `PYTHONPATH=/home/dylan/Hestia/src:/home/dylan/code/hestia-tools pytest /home/dylan/code/hestia-tools/tests/ -q`: **13 passed**

## Runtime caveat

After this change, the `job_alerts` table and tools are only available when `hestia_tools` is listed in `HestiaConfig(extra_tool_modules=["hestia_tools"])`. Existing `job_alerts` rows are preserved because the private package uses the same table name and columns. New databases will get the table lazily on the first tool call.

## Notes for next step

- Dylan/Cursor review and merge `feature/l244-migrate-job-alert-handoff` to `develop` when approved.
- Ensure the runtime Hestia config includes `extra_tool_modules=["hestia_tools"]` so the migrated tools are loaded.
