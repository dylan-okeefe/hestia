# L90 — Harden `_count_body` Cache Key

**Status:** Spec only
**Branch:** `feature/l90-count-body-cache-key` (from `develop`)

## Intent

The `_count_body` method in `context/builder.py` uses `"|".join(f"{m.role}:{m.content}")` as a cache key. If a message's content contains a literal `|system:` string (e.g., a tool result quoting a system prompt), two different message lists could produce the same cache key, causing a stale token count to be returned. While extremely unlikely in practice, this is a correctness bug in a component that controls context window budget — an incorrect count could cause silent context truncation or overflow.

The fix is trivial (use a hash-based key) and eliminates the class of bug entirely.

## Scope

### §1 — Replace string-join cache key with tuple hash

In `src/hestia/context/builder.py`, find the `_count_body` method (around line 347).

Current code:
```python
cache_key = "|".join(f"{m.role}:{m.content}" for m in messages)
```

Replace with:
```python
cache_key = hash(tuple((m.role, m.content) for m in messages))
```

This produces a collision-resistant key from the same data. `hash()` of a tuple of tuples is fast and deterministic within a Python process (sufficient for an in-memory LRU cache).

**Why not use `hashlib`?** The cache is in-memory and process-local. Python's built-in `hash()` is faster and doesn't need cryptographic properties. The key only needs to be unique within the `_tokenize_cache` OrderedDict for the lifetime of the process.

**Commit:** `fix(context): use hash-based cache key in _count_body to prevent collisions`

### §2 — Add a test

In `tests/unit/`, add a test (in an existing context builder test file or a new one) that:

1. Creates two different message lists that would produce the same `"|".join` key (one message with content `"foo|system:bar"` vs two messages `"foo"` and `"bar"` with appropriate roles).
2. Asserts that `_count_body` returns different counts for each (or at minimum, that the cache keys are different).

**Commit:** `test(context): verify _count_body cache key uniqueness`

## Evaluation

- **Spec check:** The cache key in `_count_body` no longer uses string joining with a delimiter that could appear in message content.
- **Intent check:** Two message lists that differ in content but would have collided under the old key now produce distinct cache entries. The context budgeting system cannot return a stale count due to key collision.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. Existing context builder tests still pass (they exercise `_count_body` indirectly through `build()`).

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- The new test demonstrates the collision scenario
- `.kimi-done` includes `LOOP=L90`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
