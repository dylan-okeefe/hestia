# L229 — Memory Maintenance: LLM Near-Duplicate Merge

**Goal:** Implement the infrequent LLM-assisted pass for paraphrase/near-duplicate memory merge.

**Branch:** `feature/l229-memory-llm-near-duplicate-merge`

## §0 — Depends on

Merge `feature/l228-memory-deterministic-prune` into `develop` first.

## §1 — LLM near-duplicate engine

Create `src/hestia/memory/maintenance/llm_dedupe.py`.

Class `LLMDeduper`:

- `__init__(memory_store: MemoryStore, inference: InferenceClient, max_pairs_per_run: int = 10)`
- `async def run(platform: str, platform_user: str) -> LLMDedupeResult`

Behavior:

1. Load active memories for the identity, sorted by recency, up to a configurable chunk size.
2. Skip protected memories.
3. Generate candidate pairs from the deterministic deduper's high-overlap leftovers (Jaccard 0.5–0.8) or FTS near-misses.
4. For each candidate pair, call the LLM with a prompt asking:
   - Are these two memories duplicates or near-duplicates of the same fact?
   - If yes, what is the merged content?
   - Return JSON: `{"duplicate": bool, "confidence": float, "merged_content": str | null}`
5. When `duplicate` is true and confidence >= 0.8:
   - Merge into a single memory using the LLM-provided content or a concatenation.
   - Union tags.
   - Soft-delete the loser with reason="llm-deduplicated" and reference to winner.
6. Return `LLMDedupeResult(merged_count, examined_count)`.

## §2 — Prompt

Keep the prompt in `src/hestia/memory/maintenance/prompts.py` (create). Include few-shot examples. Use `json.loads` with a fallback regex for robustness.

## §3 — MemoryMaintenance service

File: `src/hestia/memory/maintenance/service.py`

Add `async def run_llm_dedupe(self, platform, platform_user) -> LLMDedupeResult`.

## §4 — Config

File: `src/hestia/config.py`

Extend memory maintenance config with:

- `llm_dedupe_confidence_threshold: float = 0.8`
- `llm_dedupe_max_pairs_per_run: int = 10`

Wire through `AppContext` to `MemoryMaintenance` service.

## §5 — Tests

File: `tests/unit/memory/maintenance/test_llm_dedupe.py` (create)

Use a `FakeInferenceClient` returning deterministic JSON.

- `test_llm_confident_duplicate_is_merged`
- `test_llm_low_confidence_duplicate_is_left_alone`
- `test_llm_non_duplicate_is_left_alone`
- `test_protected_memories_are_skipped`

## Quality Gates

```bash
uv run pytest tests/unit/memory/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff

Write `docs/handoffs/L229-memory-llm-near-duplicate-merge-handoff.md` and update `docs/development-process/kimi-loop-log.md`.

## Critical Rules
- Confidence-gated; keep both when unsure.
- Soft-delete only.
- Protected memories are skipped.
