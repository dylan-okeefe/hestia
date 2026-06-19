# L225 — Memory-write sanitizer

**Branch:** `feature/l225-memory-write-sanitizer`
**Status:** Implementation complete; ready for orchestrator validation.

## What changed

- Added `src/hestia/memory/sanitizer.py` with `MemorySanitizer` and `SanitizerResult`.
  - Rejects empty/whitespace, below-minimum-length, pure-punctuation, and repeated-filler content.
  - Rejects tool-call XML (`<tool_call>`, `<function>`, `*_tool`), XML declarations, and any tag-like HTML/XML markup or unclosed angle brackets.
  - Rejects raw assistant/tool turn dumps via `role=` / `role:` patterns and role-marker heuristics.
  - Preserves clean prose facts and structured key-value summaries (e.g., compaction task-state summaries).
- Wired the sanitizer into `MemoryStore.save()` (`src/hestia/memory/store.py`).
  - `save()` now returns `Memory | None`.
  - Rejected writes are logged and dropped by default; `strict=True` raises `PersistenceError`.
  - Stored content is normalized (leading/trailing whitespace stripped).
- Updated `src/hestia/memory/__init__.py` to export `MemorySanitizer` and `SanitizerResult`.
- Updated `src/hestia/memory/handoff.py` to handle the new `Memory | None` return.
- Updated callers:
  - `save_memory` tool returns a graceful "Memory rejected" message.
  - CLI `memory add` echoes a rejection message instead of crashing.
- Added tests:
  - `tests/unit/memory/test_sanitizer.py` — unit tests for every rejection/acceptance rule.
  - `tests/unit/test_memory_store.py` — write-boundary integration tests including junk rejection, compaction-summary acceptance, strict mode, and whitespace normalization.
  - `tests/unit/test_memory_tools.py` — `save_memory` junk vs. clean-fact paths.
  - Updated `tests/unit/test_memory_user_scope.py` to use longer test content that clears the sanitizer's minimum-length threshold.

## Quality gates

- `uv run pytest tests/unit/memory/test_sanitizer.py tests/unit/test_memory_store.py tests/unit/test_memory_tools.py tests/unit/test_memory_user_scope.py -q`: **88 passed**
- `uv run mypy src/hestia/memory/sanitizer.py src/hestia/memory/store.py src/hestia/memory/handoff.py src/hestia/memory/__init__.py src/hestia/tools/builtin/memory_tools.py src/hestia/cli.py`: **0 errors**
- `uv run ruff check` on changed files: **clean**
- Full-suite run: 1873 passed, 6 skipped, **3 pre-existing failures** unrelated to this change:
  - `tests/unit/test_web_routes.py::TestDoctorRoute::test_doctor_check` (flaky — passed on targeted rerun)
  - `tests/unit/tools/test_browser_session_store.py::TestBrowserSessionStore::test_list_domains`
  - `tests/unit/web/test_browser_stream.py::TestStartSession::test_start_session_launches_browser_and_returns_id`

## Security scan

Ran the credential scans from `AGENTS.md` / `hestia-orchestration` skill against staged changes; no leaked secrets detected.

## Notes for next step

- L224 (`/compact` command) depends on this sanitizer being in place; the shared boundary is now protected.
- `docs/development-process/prompts/KIMI_CURRENT.md` should be advanced to L224 by the orchestrator after validation.
