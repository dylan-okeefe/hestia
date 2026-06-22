# L230 — Memory Maintenance: Contradiction / Supersession

**Branch:** `feature/l230-memory-contradiction-supersession`
**Status:** Implementation complete; ready for orchestrator validation.

## What changed

- Added `src/hestia/memory/maintenance/contradictions.py` with `SupersessionResult` and `ContradictionResolver`.
  - Loads active memories for an identity and skips the protected set (pinned, user-authored, recently recalled).
  - Generates candidate pairs from FTS near-misses using a short 3-word excerpt so semantically related memories surface even when the differing attribute is later in the sentence.
  - Calls the LLM with a structured JSON prompt (`contradiction`, `confidence`, `attribute`, `reasoning`).
  - Supersedes only when `contradiction` is true and `confidence >= threshold`, soft-deleting the older memory with `reason="superseded"` and `superseded_by` pointing to the newer memory id.
  - Appends the LLM's reasoning to the superseded memory's content before soft-deleting so the decision is auditable.
- Added the contradiction prompt, examples, and JSON parser to `src/hestia/memory/maintenance/prompts.py`.
  - Examples explicitly distinguish same-attribute updates (favorite color changed) from genuinely separate facts (two homes, job vs allergy).
- Added `MemoryMaintenance.run_contradiction_resolution(platform, platform_user)` in `src/hestia/memory/maintenance/service.py`.
- Extended `MemoryConfig` in `src/hestia/config.py` with `contradiction_confidence_threshold` and `contradiction_max_pairs_per_run`.
- Updated `src/hestia/memory/maintenance/__init__.py` to export the new API.
- Added unit tests in `tests/unit/memory/maintenance/test_contradictions.py` covering:
  - Confident contradiction supersedes the older memory.
  - Low-confidence contradiction leaves both memories active.
  - Separate facts are not treated as contradictions.
  - Protected memories are never sent to the LLM or superseded.
  - Supersession records the LLM's reasoning in the loser content.
- Hardened FTS5 query sanitization in `src/hestia/memory/store.py` to quote any query containing non-word/non-whitespace characters (e.g., periods), preventing `fts5: syntax error near '.'` when maintenance excerpts or user searches contain sentence punctuation.
  - Added a corresponding unit test in `tests/unit/test_memory_store.py`.

## Quality gates

- `uv run pytest tests/unit/memory/ -q`: **59 passed**
- `uv run mypy src/hestia`: **0 errors**
- `uv run ruff check` on changed files: **clean**
- Full-repo `uv run ruff check src/ tests/` still reports pre-existing issues in unrelated files; no new issues introduced by L230.

## Notes for next step

- L231 (trace/digest/scheduler integration) can build on the `MemoryMaintenance.run_contradiction_resolution` entry point.
- `docs/development-process/prompts/KIMI_CURRENT.md` should be advanced to L231 by the orchestrator after validation.
