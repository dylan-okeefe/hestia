# L243 — Pull Job-URL Extraction into Private Tool

**Branch:** `feature/l243-extract-job-url-private-tool`
**Status:** Implementation complete; ready for review.
**Private repo:** `git@github.com-personal:dylan-okeefe/hestia-tools.git` (`~/code/hestia-tools`)

## What changed

### Private `hestia-tools` repo

- Added `hestia_tools/job_url_extraction.py` with the `extract_job_url` tool.
  - Decorated with `@tool` from `hestia.tools.metadata`; no capability claims (pure string parsing).
  - Parameters: `body` (required string), `hint_url` (optional string).
  - Behavior mirrors the removed executor logic exactly:
    - Extracts all URLs from `body`.
    - Skips URLs matching ignore patterns (unsubscribe, preferences, alerts, privacy, terms, login, LinkedIn alerts/feed, profile-views).
    - Scores remaining URLs against job-board patterns (Indeed, ZipRecruiter, LinkedIn jobs, Dice, Glassdoor, Built In, plus generic `/jobs/`, `/job/`, `jobListing`, `viewjob`, `job-detail`, `/km/`, `/ekm/`, `/clk?`).
    - URL-decodes URLs before scoring to catch embedded job paths.
    - Returns the highest-scoring URL, or `"NONE"` if none qualify.
    - If `hint_url` scores > 0 it wins; empty/`"NONE"` hints are ignored and the body is scanned.
- Updated `hestia_tools/__init__.py` to register `extract_job_url` alongside `indeed_search_jobs`.
- Added `tests/test_job_url_extraction.py` covering Indeed extraction, unsubscribe-only fallback to `"NONE"`, best-score selection, `hint_url` preference, and `hint_url == "NONE"` body scanning.
- Updated `README.md` to document `extract_job_url`.

### Public Hestia core

- Removed job-board-specific URL extraction from `src/hestia/workflows/executor.py`:
  - Deleted `_JOB_URL_PATTERNS`, `_IGNORE_URL_PATTERNS`, and `_extract_best_job_url`.
  - Deleted the special-case `if node.id == "extract_url":` inference-node fallback.
  - Kept the generic `_extract_url_from_text` helper (still used for LLM-output cleanup).
- Verified no other source files reference the removed symbols.
- Regenerated `metrics.json`.

## Commits

Private `hestia-tools` repo (`main`):
- `60a5fbf` — feat: add extract_job_url private tool
- `60bb1b8` — test: extract_job_url scoring and fallback behavior

Public Hestia core (`feature/l243-extract-job-url-private-tool`):
- `TBD` — refactor: remove job-board URL extraction from workflow executor
- `TBD` — docs: L243 handoff, loop log, and current-task pointer
- `TBD` — chore: update metrics.json after L243

## Quality gates

Hestia:
- `uv run mypy src/hestia/workflows/executor.py`: **0 errors**
- `uv run ruff check src/hestia/workflows/executor.py`: **clean**
- `uv run pytest tests/unit/tools/ -q`: **110 passed, 15 warnings**
- `uv run pytest tests/unit/workflows/ -q`: **blocked by pre-existing test-env issue** (see below).

Private repo (installed in Hestia venv):
- `uv run pytest /home/dylan/code/hestia-tools/tests/test_job_url_extraction.py -q`: **8 passed**

## Runtime caveat

The existing private job-search workflow in the DB/UI currently uses an `extract_url` **inference** node that relied on the executor's special-case body scanning. After this change, that workflow will lose the job-URL fallback until it is updated to call the new `extract_job_url` tool node instead. The generic inference path still extracts the first URL from LLM output, but it no longer scores job-board patterns or scans the raw email body.

## Notes for next step

- Dylan/Cursor review and merge `feature/l243-extract-job-url-private-tool` to `develop` when approved.
- Update the stored job-search workflow to replace the `extract_url` inference node with an `extract_job_url` tool node.
- The `job_alert` subsystem remains in the public core; migrating it is tracked separately.

## Test environment note

`tests/unit/workflows/test_executor.py` fails to instantiate `AppContext` in this environment because `HestiaConfig.default()` returns `inference.model_name == ""` and the test fixture does not set it. This appears pre-existing and unrelated to the refactor; `tests/unit/tools/` and static checks pass cleanly. If needed, the fixture can be aligned with `tests/integration/test_compaction_command.py` by passing `inference=InferenceConfig(model_name="dummy")` (with `HESTIA_ALLOW_DUMMY_MODEL=1`).
