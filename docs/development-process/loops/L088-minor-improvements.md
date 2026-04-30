# L88 — Minor Improvements (April 29 Code Review)

**Status:** In progress  
**Branch:** `feature/l88-april-29-minor-improvements` (from `develop`)  
**Scope:** Memory hygiene and readability. Small, self-contained changes.

---

## Items

| ID | Issue | File | Fix |
|----|-------|------|-----|
| I1 | `SessionRateLimiter._buckets` unbounded growth | `src/hestia/core/rate_limiter.py` | Add max-size eviction (LRU or periodic sweep) |
| I2 | `style/builder.py` SQL unreadable | `src/hestia/style/builder.py` | Reformat: blank lines between methods, multi-line triple-quoted SQL |

---

## I1 Detail: Rate limiter bucket eviction

`SessionRateLimiter._buckets: dict[str, TokenBucket] = {}` grows without bound. Every unique `session_id` gets a `TokenBucket` that is never evicted.

Fix: Add max-size eviction. Since the rate limiter is gated behind `config.rate_limit.enabled` (default `False`), a simple LRU approach is sufficient:

- Use `dict` ordered-preservation (Python 3.7+) as an LRU: when inserting a new bucket beyond `max_buckets`, evict the oldest key.
- Or use a `collections.OrderedDict` / `functools.lru_cache` pattern.
- Default `max_buckets` to something reasonable (e.g., 10,000) or read from config if a field exists.

If adding a config field, wire it through `RateLimitConfig` and default it.

## I2 Detail: style/builder.py readability

At 99 lines, every method runs together with no blank lines, and SQL queries are single-line strings with `# noqa: E501`. Break SQL into multi-line triple-quoted strings with aligned JOIN conditions. Add blank lines between methods. Zero behavior change.

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- `pytest` green
- `mypy` 0 errors in changed files
- `ruff` at baseline or better
- `.kimi-done` includes `LOOP=L88`

## Handoff

- Write `docs/handoffs/L88-april-29-minor-improvements-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
