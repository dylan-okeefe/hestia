# L98 — Token Counting Batch Optimization

**Status:** Spec only
**Branch:** `feature/l98-token-batch` (from `develop`)

## Intent

The `ContextBuilder._count_body` method makes one POST `/tokenize` call per unique message in the history. For a 50-message history with 40 unique messages, that's 40 sequential HTTP round-trips to llama-server — roughly 400ms of latency per turn, all spent on token counting rather than inference.

The llama-server `/tokenize` endpoint accepts a single string. By concatenating messages with a known separator and making one call, we can reduce N round-trips to 1. The per-message counts can be recovered by subtracting separator overhead.

This is the single largest latency optimization available in the context-building path. It directly improves turn response time for conversations with long histories.

## Scope

### §1 — Add a batch tokenization method to InferenceClient

In `src/hestia/core/inference.py`, add a method:

```python
async def tokenize_batch(self, texts: list[str]) -> list[int]:
    """Tokenize multiple strings in a single HTTP call.
    
    Concatenates texts with a known separator, tokenizes the whole
    thing, then recovers per-text counts by subtracting separator
    overhead.
    
    Returns a list of token counts, one per input text.
    """
```

Implementation approach:
1. Choose a separator that won't appear in normal text. Use a special token if llama-server supports it, otherwise use a distinctive string like `"\n<|SEP|>\n"`.
2. Pre-compute the separator's token count once (cache it like `_compute_join_overhead` does).
3. Concatenate all texts with the separator.
4. Make one POST `/tokenize` call.
5. The result is the total token count. To recover per-text counts: tokenize each text's prefix up to each separator boundary. **Alternatively**, if the response includes the token IDs (not just the count), scan for separator token IDs to find boundaries.

**Important:** Check what llama-server's `/tokenize` endpoint actually returns. If it returns token IDs (not just a count), the separator approach is straightforward — find separator token positions and count between them. If it returns only a count, you'll need a different approach (e.g., prefix sums with cumulative tokenization).

Read the llama-server API docs or test the endpoint before implementing. The approach depends on the response format.

**Fallback:** If batch tokenization proves unreliable (separator tokens vary by model, edge cases with BPE boundaries), keep the existing per-message path as a fallback behind a config flag.

**Commit:** `feat(inference): add tokenize_batch for single-call token counting`

### §2 — Wire batch tokenization into ContextBuilder

In `src/hestia/context/builder.py`, modify `_count_body` to use the batch method when available:

1. Collect all unique messages that aren't in `_tokenize_cache`
2. Call `tokenize_batch` with all their contents at once
3. Populate `_tokenize_cache` from the results
4. Return the sum as before

The cache still works — you're just filling it with one call instead of N. Messages already in cache are skipped.

**Commit:** `feat(context): use batch tokenization in _count_body`

### §3 — Add tests

1. Unit test `tokenize_batch` with known inputs — verify per-text counts sum correctly.
2. Integration test that `_count_body` with batch produces the same result as `_count_body` without batch (compare against the existing per-message path).

**Commit:** `test(context): verify batch tokenization accuracy`

## Evaluation

- **Spec check:** `InferenceClient.tokenize_batch` exists. `_count_body` uses it to count tokens in a single HTTP call instead of N calls.
- **Intent check:** A 50-message history that previously required ~40 HTTP round-trips for token counting now requires 1 (plus cache lookups for previously-seen messages). Turn latency is reduced by ~300-400ms for long conversations. The cache still works — subsequent turns reuse cached counts for messages already seen.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. The batch path produces the same token counts as the per-message path (verified by the comparison test). If the batch path fails at runtime, the fallback per-message path still works.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- The comparison test proves batch and per-message counts match
- `.kimi-done` includes `LOOP=L98`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
