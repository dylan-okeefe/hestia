# L67 — Bounded Caches & Daemon Stability

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l67-bounded-caches-and-daemon-stability` (from `develop`)

## Goal

Bound the three unbounded memory accumulators identified in the evaluation: the tokenize cache in `ContextBuilder`, the edit-time tracker in `TelegramAdapter`, and the redundant `join_overhead` recomputation.

---

## Intent & Meaning

The evaluation found three sources of unbounded growth:

1. `ContextBuilder._tokenize_cache` — a plain `dict` keyed on `(role, content)`. Over days of daemon uptime (Telegram/Matrix), every unique message ever seen accumulates. No eviction, no size limit, no TTL.
2. `TelegramAdapter._last_edit_times` — a plain `dict[msg_id, timestamp]`. Message IDs are lightweight, but over weeks it is still a slow leak.
3. `_compute_join_overhead` — two tokenize calls on the first `build()` per `ContextBuilder` instance. Since the builder is created per-app, this is minor, but it is unnecessary work.

The intent is **operational hygiene for long-running processes**. Hestia is designed to run as a daemon. A daemon that grows memory without bound eventually gets OOM-killed or forces a restart. The fix is not about preventing OOM today (the evaluation notes it's "unlikely to cause OOM" for a personal assistant) — it is about **removing the category of problem entirely**. Bounded caches are proof that the code was written with daemon lifecycles in mind.

---

## Scope

### §1 — `ContextBuilder._tokenize_cache` → LRU

**File:** `src/hestia/context/builder.py`
**Evaluation:** `_tokenize_cache` is a plain dict keyed on `(role, content)`. Grows without bound.

**Change:**
Replace the dict with `functools.lru_cache` on the `_count_tokens` method, or use a bounded dict with `collections.OrderedDict` if the cache needs to live on the instance.

```python
# Option A: LRU on the method
from functools import lru_cache

# If _count_tokens can be made a staticmethod or standalone function:
@lru_cache(maxsize=4096)
def _count_tokens_cached(inference: InferenceClient, role: str, content: str) -> int:
    ...

# Option B: Bounded OrderedDict on the instance
from collections import OrderedDict

self._tokenize_cache: OrderedDict[tuple[str, str], int] = OrderedDict()
# On insert:
if key in self._tokenize_cache:
    self._tokenize_cache.move_to_end(key)
else:
    self._tokenize_cache[key] = count
if len(self._tokenize_cache) > 4096:
    self._tokenize_cache.popitem(last=False)
```

**Intent:** Cap memory usage at a known ceiling. 4096 entries × ~100 bytes ≈ 400KB — trivial, but bounded.

**Commit:** `fix(context): bound tokenize cache with LRU eviction`

---

### §2 — `TelegramAdapter._last_edit_times` → bounded TTL

**File:** `src/hestia/platforms/telegram_adapter.py`
**Evaluation:** `_last_edit_times` dict grows without bound.

**Change:**
Periodically evict entries older than a reasonable threshold (e.g., 1 hour). Simplest approach: on each access or on a timer, remove entries where `now - ts > 3600`.

```python
_MAX_EDIT_TRACK_AGE = 3600.0

def _prune_edit_times(self) -> None:
    cutoff = time.monotonic() - _MAX_EDIT_TRACK_AGE
    stale = [k for k, v in self._last_edit_times.items() if v < cutoff]
    for k in stale:
        del self._last_edit_times[k]
```

Call `_prune_edit_times()` inside `_send_typing_indicator()` or before each edit check.

**Intent:** Message IDs are cheap, but "grows forever" is a pattern that should not exist in daemon code. A 1-hour window covers all realistic edit-debouncing scenarios.

**Commit:** `fix(telegram): prune stale entries from _last_edit_times`

---

### §3 — Cache `_join_overhead` permanently

**File:** `src/hestia/context/builder.py`
**Evaluation:** `_compute_join_overhead` does two tokenize calls every time `_join_overhead` is `None`. This happens on first `build()`.

**Change:**
Ensure `_join_overhead` is computed once and never reset. If it is currently lazily computed, confirm the laziness is correct; if it is recomputed under any condition, make it permanently cached.

**Intent:** The overhead of joining two messages is a constant for a given model/tokenizer. Recomputing it is wasted HTTP round-trips.

**Commit:** `perf(context): permanently cache join_overhead after first computation`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `ContextBuilder._tokenize_cache` has a max size (e.g., 4096).
- `TelegramAdapter._last_edit_times` evicts entries older than 1 hour.
- `_join_overhead` is computed at most once per `ContextBuilder` instance.

## Acceptance (Intent-Based)

- **Memory usage is predictable after 10,000 turns.** A synthetic test that feeds 10,000 unique messages through `ContextBuilder` should show stable memory, not linear growth.
- **The Telegram adapter does not leak message IDs over a simulated week.** A test that injects 100,000 synthetic message IDs with timestamps spread across 48 hours should retain only the recent ones.
- **The cache bounds are visible in code, not magic.** A reader should see `maxsize=4096` or `3600.0` as named constants, not infer them from behavior.

## Handoff

- Write `docs/handoffs/L67-bounded-caches-and-daemon-stability-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l67-bounded-caches-and-daemon-stability` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
