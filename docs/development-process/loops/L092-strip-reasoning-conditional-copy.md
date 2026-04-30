# L92 — Optimize `_strip_historical_reasoning` with Conditional Copy

**Status:** Spec only
**Branch:** `feature/l92-strip-reasoning-optimization` (from `develop`)

## Intent

`_strip_historical_reasoning` in `core/inference.py` (lines ~13–31) creates a new `Message` object for every message in the history list, even if the message has no `reasoning_content` to strip. For a 50-message history, that's 50 unnecessary object allocations per inference call. While cheap individually, this runs on every `chat()` and `count_request()` call — potentially multiple times per turn.

The optimization is to only copy messages that actually have `reasoning_content` set, passing through the rest unchanged. This is a micro-optimization, but it's trivial to implement and makes the hot path cleaner.

## Scope

### §1 — Conditional copy in `_strip_historical_reasoning`

In `src/hestia/core/inference.py`, find `_strip_historical_reasoning`.

Current pattern (creates a copy for every message):
```python
def _strip_historical_reasoning(messages: list[Message]) -> list[Message]:
    return [Message(role=m.role, content=m.content, ...) for m in messages]
```

Replace with conditional copy — only allocate a new `Message` when `reasoning_content` is set:
```python
def _strip_historical_reasoning(messages: list[Message]) -> list[Message]:
    result = []
    for m in messages:
        if m.reasoning_content:
            result.append(dataclasses.replace(m, reasoning_content=None))
        else:
            result.append(m)
    return result
```

Use `dataclasses.replace()` instead of manual `Message(...)` construction. This is more maintainable — if fields are added to `Message`, `dataclasses.replace` automatically includes them. Import `dataclasses` at the top of the file if not already imported.

**Why `dataclasses.replace` instead of manual construction?** The current manual construction must list every `Message` field. If a field is added to `Message` and not added here, it's silently dropped. `dataclasses.replace` copies all fields and only overrides the ones you specify.

**Commit:** `perf(inference): skip message copy when no reasoning_content to strip`

## Evaluation

- **Spec check:** `_strip_historical_reasoning` only allocates new `Message` objects for messages that have `reasoning_content` set. Messages without it are passed through as-is.
- **Intent check:** The hot path (most messages don't have reasoning content) avoids unnecessary allocations. The function still strips reasoning content when present. Using `dataclasses.replace` means future `Message` field additions won't be silently dropped.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. If there are existing tests for `_strip_historical_reasoning`, they still pass.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `_strip_historical_reasoning` uses `dataclasses.replace` for copies
- `.kimi-done` includes `LOOP=L92`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
