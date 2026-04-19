# Kimi loop L32c — `ContextBuilder` per-message `/tokenize` cache

## Hard step budget

≤ **5 commits**, ≤ **1 new test module**, no exploration outside `src/hestia/context/builder.py` and its tests + the new ADR. Stop after the handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L32b (merged at `e74ed46`):

- Test baseline: **708 passed, 6 skipped**.
- Mypy 0. Ruff 44 — must not regress.
- Prefix-layer registry (`_PrefixLayer`) is the assembly path now — touch `_prefix_layers()` if you need to invalidate per-prefix.
- `ContextBuilder.build()` no longer accepts `*_prefix` kwargs — use the setters.

From the external code-quality review:

- `ContextBuilder.build()` makes **O(N) `/tokenize` HTTP calls** during history trimming — one round trip per candidate message. For a 200-turn session that's 200 round trips before inference. The candidate strings (`protected + included + [msg] + protected_bottom`) recompute the entire token count from scratch each iteration.
- Messages are immutable from the builder's perspective; per-message counts can be cached for the lifetime of the builder instance.

**Branch:** `feature/l32c-context-tokenize-cache` from `develop` post-L32b.

**Target version:** **0.7.8** (patch — pure perf refactor).

---

## Scope

### §1 — Add per-message tokenize cache

In `src/hestia/context/builder.py`:

- Add `self._tokenize_cache: dict[tuple[str, str], int] = {}` keyed on `(message.role, message.content)`. (Content-hash keying survives across rebuilds in the same session; `id(message)` does not, because the orchestrator may rebuild Message objects between turns.)
- Wrap the existing `/tokenize` call in:

  ```python
  async def _count_tokens(self, message: Message) -> int:
      key = (message.role, message.content or "")
      if key in self._tokenize_cache:
          return self._tokenize_cache[key]
      count = await self._inference.tokenize(self._render_message(key))  # whatever the existing single-message render is
      self._tokenize_cache[key] = count
      return count
  ```

- During the trim loop, sum cached per-message counts plus a **constant `_join_overhead`** (computed once per build — measure once on a 2-message join, store on `self`) instead of POSTing the concatenated candidate string each iteration.
- Document the join-overhead approximation in a comment: total trim-window tokens ≈ `sum(_count_tokens(m) for m in window) + (len(window) - 1) * join_overhead`. Acceptable error: ±1 token vs the joined-string ground truth.

### §2 — Cache invalidation

- The cache survives across `build()` calls for the same builder instance — that's the point.
- Setters (`set_identity_prefix` etc.) do **not** invalidate the message cache (they touch prefixes, not messages).
- If the inference client URL/model changes, callers should construct a new builder. Document this in the docstring; do **not** add reactive invalidation logic.

### §3 — Tests

`tests/unit/test_context_builder_tokenize_cache.py`:

- `test_tokenize_cache_hits_on_repeated_build` — patch `inference.tokenize` with a counter; build twice with the same 10 messages; assert the second build issues **0** new tokenize calls.
- `test_tokenize_cache_invalidation_on_new_message` — build with 10 messages, append an 11th, build again; assert exactly **1** new tokenize call.
- `test_total_tokens_matches_joined_string_baseline` — for a synthetic 50-message conversation, run the trim with the cache and a reference function that always tokenizes the joined string; the selected window must match (or differ by ≤ 1 message at the boundary, which is acceptable since the new code uses the join-overhead approximation).
- `test_role_and_content_are_the_cache_key` — two messages with same role+content but distinct `created_at` ⇒ same cache hit (one tokenize call).

Existing `tests/unit/test_context_builder*.py` must stay green.

### §4 — ADR-0021

`docs/adr/ADR-0021-context-builder-prefix-registry-and-tokenize-cache.md`:

Cover both the L32b registry pattern and the L32c cache:

- **Status:** Accepted (in v0.7.7 for the registry, v0.7.8 for the cache).
- **Context:** monolithic `build()` had four parallel prefix conditionals + an O(N) tokenize loop.
- **Decision:** prefix layers are an ordered registry; tokenize is content-keyed cached for the builder lifetime; trim uses cached sums + a constant join-overhead.
- **Consequences:** ~99% fewer tokenize calls on a typical session; adding a new prefix layer is one-line to the registry plus a setter; the cache assumes message content is treated as immutable by callers.

### §5 — Version bump + handoff

- `pyproject.toml` → `0.7.8`.
- `uv lock`.
- CHANGELOG entry under `[0.7.8] — 2026-04-18`.
- `docs/handoffs/L32-context-rework-handoff.md` — single handoff covering the L32a + L32b + L32c arc; reference all three loop specs and final test/mypy/ruff numbers.

---

## Commits (5 total)

1. `perf(context): cache /tokenize results per Message; constant join overhead`
2. `test(context): cache hits, invalidation, parity with joined-string baseline`
3. `docs(adr): ADR-0021 prefix registry + tokenize cache`
4. `chore(release): bump to 0.7.8`
5. `docs(handoff): L32 context rework arc (L32a + L32b + L32c)`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L32c
BRANCH=feature/l32c-context-tokenize-cache
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Pure perf refactor. No new prefix layers. No new public API on `ContextBuilder`.
- Cache key is `(role, content)`. Do not over-engineer with WeakRefs or LRU eviction; bounded by session size.
- Push and stop.
