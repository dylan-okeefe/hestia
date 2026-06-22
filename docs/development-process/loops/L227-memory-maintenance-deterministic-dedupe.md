# L227 — Memory Maintenance: Deterministic Dedupe

**Goal:** Implement the frequent deterministic dedupe pass: exact normalized-text match and high-overlap FTS similarity, merging duplicates into the richer/newer memory and soft-deleting the loser.

**Branch:** `feature/l227-memory-deterministic-dedupe`

## §0 — Depends on

Merge `feature/l226-memory-soft-delete-protected` into `develop` first.

## §1 — Dedupe engine

Create `src/hestia/memory/maintenance/dedupe.py`.

Class `DeterministicDeduper`:

- `__init__(memory_store: MemoryStore)`
- `async def run(platform: str, platform_user: str) -> DedupeResult`

Behavior:

1. Load all active memories for the identity via `memory_store.list_active_memories(platform=..., platform_user=..., limit=high)`.
2. Skip protected memories (`memory_store.is_protected`).
3. Group candidates by normalized content hash:
   - Lowercase, strip whitespace, collapse spaces.
   - For each group with >1 memory, merge them.
4. For remaining unmerged memories, run FTS overlap pairs:
   - For each memory, `memory_store.search` with a sanitized excerpt of its content.
   - If a different memory ranks in top results and has high token/word overlap (e.g., Jaccard > 0.8), merge.
5. Merge action:
   - Pick the winner: newer `created_at`; if tied, longer content; if tied, lower id.
   - Winner content = winner content + "\n\n" + loser content (or concatenate unique lines).
   - Winner tags = union of both tag sets.
   - Update winner content/tags in place (add `memory_store.update` method).
   - Soft-delete loser with reason="deduplicated" and a reference to winner id.

Return `DedupeResult(merged_count, skipped_protected_count)`.

## §2 — MemoryStore update method

File: `src/hestia/memory/store.py`

Add `async def update(self, memory_id, content=None, tags=None) -> bool` to mutate content/tags of an active memory.

## §3 — Tests

File: `tests/unit/memory/maintenance/test_deterministic_dedupe.py` (create)

- `test_exact_duplicates_are_merged`
- `test_high_overlap_fts_duplicates_are_merged`
- `test_protected_memories_are_skipped`
- `test_non_duplicates_are_left_alone`
- `test_merge_uses_newer_and_unions_tags`

## §4 — Wiring stub (optional)

Add a `MemoryMaintenance` service stub in `src/hestia/memory/maintenance/service.py` that exposes `async def run_deterministic_dedupe(platform, platform_user)` delegating to `DeterministicDeduper`. This gives later loops a stable entry point.

## Quality Gates

```bash
uv run pytest tests/unit/memory/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff

Write `docs/handoffs/L227-memory-deterministic-dedupe-handoff.md` and update `docs/development-process/kimi-loop-log.md`.

## Critical Rules
- Never hard-delete; always soft-delete with reason.
- Protected memories are skipped entirely.
- Update winner in place so only the loser gets deleted.
