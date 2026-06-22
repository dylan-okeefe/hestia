# L230 — Memory Maintenance: Contradiction / Supersession

**Goal:** Implement the LLM-assisted contradiction detection pass: when two active memories conflict on the same attribute, the newer fact supersedes the older.

**Branch:** `feature/l230-memory-contradiction-supersession`

## §0 — Depends on

Merge `feature/l229-memory-llm-near-duplicate-merge` into `develop` first.

## §1 — Contradiction engine

Create `src/hestia/memory/maintenance/contradictions.py`.

Class `ContradictionResolver`:

- `__init__(memory_store: MemoryStore, inference: InferenceClient, confidence_threshold: float = 0.8)`
- `async def run(platform: str, platform_user: str) -> SupersessionResult`

Behavior:

1. Load active memories for the identity.
2. Skip protected memories.
3. Generate candidate pairs from overlapping FTS queries or content embeddings (reuse FTS).
4. For each pair, ask the LLM:
   - Do these two memories contradict on the same attribute?
   - If yes, which is newer and should win?
   - Return JSON: `{"contradiction": bool, "confidence": float, "attribute": str | null, "reasoning": str | null}`
5. When `contradiction` is true and confidence >= threshold:
   - Soft-delete the older memory with reason="superseded" and `superseded_by` pointing to the newer memory id.
   - Add a note to the older memory content or a separate trace field recording the reasoning.
6. Return `SupersessionResult(superseded_count, examined_count)`.

## §2 — Prompt

Add prompt to `src/hestia/memory/maintenance/prompts.py`. Include examples distinguishing same-attribute updates from genuinely separate facts (e.g., two homes).

## §3 — MemoryMaintenance service

File: `src/hestia/memory/maintenance/service.py`

Add `async def run_contradiction_resolution(self, platform, platform_user) -> SupersessionResult`.

## §4 — Config

File: `src/hestia/config.py`

Extend memory maintenance config with:

- `contradiction_confidence_threshold: float = 0.8`
- `contradiction_max_pairs_per_run: int = 10`

Wire through `AppContext`.

## §5 — Tests

File: `tests/unit/memory/maintenance/test_contradictions.py` (create)

Use a `FakeInferenceClient` returning deterministic JSON.

- `test_confident_contradiction_supersedes_older`
- `test_low_confidence_contradiction_keeps_both`
- `test_separate_facts_are_not_contradictions`
- `test_protected_memory_never_superseded`
- `test_supersession_records_reasoning`

## Quality Gates

```bash
uv run pytest tests/unit/memory/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff

Write `docs/handoffs/L230-memory-contradiction-supersession-handoff.md` and update `docs/development-process/kimi-loop-log.md`.

## Critical Rules
- Only act when confident it's the same attribute.
- Soft-delete the older with `superseded_by` and reasoning.
- Supersessions are the riskiest auto-decision; record full reasoning.
