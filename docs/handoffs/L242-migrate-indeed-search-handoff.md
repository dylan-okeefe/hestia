# L242 — Migrate `indeed_search_jobs` to Private Repo

**Branch:** `feature/l242-migrate-indeed-search`
**Status:** Implementation complete; ready for review.
**Private repo:** `git@github.com-personal:dylan-okeefe/hestia-tools.git` (`~/code/hestia-tools`)

## What changed

### Public Hestia core

- Made `http_get_impl` public in `src/hestia/tools/builtin/http_get.py` so external tool modules can reuse the SSRF-guarded HTTP fetch path.
  - Renamed `_http_get_impl` → `http_get_impl` and updated internal call sites.
  - Kept a backward-compatible alias `_http_get_impl = http_get_impl`.
- Removed `src/hestia/tools/builtin/indeed_search.py` from the public core.
- Updated `src/hestia/tools/builtin/__init__.py` to drop the `indeed_search_jobs` import and `__all__` entry.
- Updated `src/hestia/app.py` to remove the `indeed_search_jobs` import and `reg.register(...)` call.
- Regenerated `metrics.json`.

### Private `hestia-tools` repo

- Added `hestia_tools/indeed_search.py` (migrated from Hestia public core).
  - Scrubbed personal taxonomy (removed "A-IN-1" from docstring and `public_description`).
  - Imports public `http_get_impl` from Hestia.
- Added `register(registry)` in `hestia_tools/__init__.py`.
- Added `tests/test_indeed_search.py` verifying tool name, capabilities, and taxonomy scrub.
- Added `hestia` as a runtime dependency and documented how to run tests inside Hestia's venv.

## Commits

Public Hestia core (`feature/l242-migrate-indeed-search`):
- `0f6d57cc` — feat: make http_get_impl public for external tool modules
- `58977a0b` — refactor: remove indeed_search_jobs from public core
- `f3ac05ee` — chore: update metrics.json after indeed_search migration

Private `hestia-tools` repo (`main`):
- `4205d7a` — feat: migrate indeed_search_jobs from Hestia public core
- `c3afefb` — test: indeed_search metadata and taxonomy scrub
- `51ea6c1` — docs: add hestia dependency and test instructions

## Quality gates

Hestia:
- `uv run pytest tests/unit/tools/test_external_tool_modules.py tests/unit/tools/test_external_tool_setup.py -q`: **11 passed**
- `uv run pytest tests/unit/tools/ -q`: **110 passed, 15 warnings**
- `uv run mypy src/hestia/tools/builtin/http_get.py src/hestia/app.py src/hestia/tools/builtin/__init__.py`: **0 errors**
- `uv run ruff check src/hestia/tools/builtin/http_get.py src/hestia/app.py src/hestia/tools/builtin/__init__.py`: **clean**

Private repo (installed in Hestia venv):
- `uv run pytest /home/dylan/code/hestia-tools/tests/ -q`: **1 passed**

## Notes for next step

- Dylan/Cursor review and merge `feature/l242-migrate-indeed-search` to `develop` when approved.
- The remaining four job-search tools (`builtin_search`, `dice_search`, `linkedin_search`, `ziprecruiter_search`) still live on the unmerged `feature/job-search-tools` branch. They can be migrated to `hestia-tools` using the same pattern once this migration is approved.
- The `job_alert` subsystem remains in the public core; moving it requires the persistence seam from L241 plus a private-repo `setup(context)` hook.
- No merge or push of the Hestia feature branch was performed yet.
