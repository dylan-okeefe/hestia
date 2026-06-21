# L229 Handoff — Memory Maintenance: LLM Near-Duplicate Merge

**Outcome:** Implemented the infrequent LLM-assisted maintenance pass that reviews paraphrase/near-duplicate memory pairs and merges them when the model is highly confident.

**Branch:** `feature/l229-memory-llm-near-duplicate-merge`

## What changed

- Added `src/hestia/memory/maintenance/llm_dedupe.py`:
  - `LLMDedupeResult(merged_count, examined_count)` dataclass.
  - `LLMDeduper` loads active memories, skips protected memories, and generates candidate pairs from FTS near-misses filtered by Jaccard 0.5–0.8 (the leftover band not already merged by the deterministic deduper).
  - Each candidate pair is sent to the LLM with a structured JSON prompt asking for `duplicate`, `confidence`, and optional `merged_content`.
  - When `duplicate` is true and `confidence >= 0.8`, the loser is soft-deleted with `reason="llm-deduplicated"` and a reference to the winner; the winner is updated with the merged content and a union of tags.
  - Unconfident or non-duplicate judgments leave both memories active.

- Added `src/hestia/memory/maintenance/prompts.py`:
  - System prompt with few-shot examples and a strict JSON schema.
  - `build_llm_dedupe_prompt(memory_a, memory_b)`.
  - `parse_llm_dedupe_response(text)` tries `json.loads` first and falls back to a regex object extraction; unparseable responses are treated as non-duplicates.

- Updated `src/hestia/memory/maintenance/service.py`:
  - `MemoryMaintenance` now accepts an optional `InferenceClient` and `MemoryConfig`.
  - Added `run_llm_dedupe(platform, platform_user)`.

- Updated `src/hestia/config.py`:
  - `MemoryConfig` gained `llm_dedupe_confidence_threshold: float = 0.8` and `llm_dedupe_max_pairs_per_run: int = 10`.

- Updated `src/hestia/app.py`:
  - Added a lazy `memory_maintenance` cached property on `AppContext` that wires `MemoryStore`, `InferenceClient`, and `MemoryConfig`.

- Added `tests/unit/memory/maintenance/test_llm_dedupe.py`:
  - `FakeInferenceClient` subclass that returns deterministic JSON responses.
  - Tests for confident merge, low-confidence leave-alone, non-duplicate leave-alone, and protected-memory skipping.

## Quality gates

- `uv run pytest tests/unit/memory/ -q` — 54 passed.
- `uv run mypy src/hestia` — 0 errors.
- `uv run ruff check src/ tests/` — clean on all L229 files; full-repo ruff still reports pre-existing issues in unrelated files, no new issues introduced by L229.

## Next steps

- Cursor review and merge into `feature/l228-memory-deterministic-prune` lineage (do not merge to `develop` until L226-L228 are ready).
- Advance `KIMI_CURRENT.md` to L230 (Memory Maintenance: Contradiction Supersession).
