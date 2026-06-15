# L218 Handoff: Chunked Large-File Writes

## Status
Implemented on `feature/develop-review-2026-06-12`.

## Changes Made
- Updated the default system prompt in `src/hestia/config.py` to teach the chunked-write protocol (header via `write_file`, sections via `append_to_file`) for content over 2000 characters.
- Updated `config.runtime.py` with the same rule and a concrete job-search chunked-write example.
- Updated `write_file` and `append_to_file` public descriptions in `src/hestia/tools/builtin/write_file.py` and `src/hestia/tools/builtin/append_to_file.py` to mention the 2000-character limit.
- Updated the `call_tool` meta-tool description in `src/hestia/tools/registry.py` to repeat the chunked-write rule.
- Replaced the generic `TRUNCATED_WRITE_FILE` correction in `src/hestia/orchestrator/quality.py` with a recovery flow:
  - `_recover_truncated_write_file()` extracts the tool name, path, and partial `content` from an unclosed XML block.
  - `_handle_truncated_write_file()` writes the partial content using the registered `write_file` or `append_to_file` handler and builds a correction that tells the model where the content was saved and to continue with `append_to_file`.
  - Falls back to the generic correction when recovery or the write fails (e.g. path outside allowed roots).
- Wired the recovery handlers through `src/hestia/orchestrator/execution.py` `_classify_and_maybe_correct()` by passing the registered tool handlers to `classify_turn()`.
- Added/updated tests in:
  - `tests/unit/test_config.py`
  - `tests/unit/tools/test_registry.py`
  - `tests/unit/orchestrator/test_quality.py`
  - `tests/unit/core/test_regression_xml_tool_calls.py`

## Quality Gates
- `uv run pytest tests/unit/ tests/integration/ -q`: 3 pre-existing failures, no new failures.
- `uv run mypy src/hestia`: no new errors introduced.
- `uv run ruff check src/ tests/`: no new lint errors introduced.

## Pre-existing Baseline Failures (not introduced by L189)
- `tests/unit/test_web_routes.py::TestDoctorRoute::test_doctor_check`
- `tests/unit/tools/test_browser_session_store.py::TestBrowserSessionStore::test_list_domains`
- `tests/unit/web/test_browser_stream.py::TestStartSession::test_start_session_launches_browser_and_returns_id`

## Review Carry-forward
- The recovery regex is intentionally lenient. When the model emits arguments out of order (e.g. `"content"` before `"path"`, as in `write_file_unclosed_huge.xml`) or omits the path entirely, recovery falls back to the generic correction. A more robust prefix JSON parser could improve recovery rates if this keeps happening.
- Only `path` and `content` are recovered; other arguments are ignored.
- The truncated-write classifier threshold (1500 chars) and the chunked-write limit (2000 chars) are intentionally separate; monitor real model output to tune them.
- For a truncated `append_to_file`, the current recovery overwrites the file if a path is present. Revisit whether appending is safer when the file already exists.
- Consider surfacing recovered partial files as artifacts or in the UI so users know a partial save occurred.
