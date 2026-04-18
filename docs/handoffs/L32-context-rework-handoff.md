# L32 Context Rework Arc — Handoff

## Scope

This handoff covers the three mini-loops that refactored `ContextBuilder`:

- **L32a** — delete dead `TurnState` and `ToolResult` from `core/types.py`
- **L32b** — replace per-call `*_prefix` kwargs with an ordered `_PrefixLayer` registry
- **L32c** — add per-message `/tokenize` cache + constant join-overhead approximation

## Specs

- `docs/development-process/kimi-loops/L32a-delete-dead-types.md`
- `docs/development-process/kimi-loops/L32b-context-prefix-registry.md`
- `docs/development-process/kimi-loops/L32c-context-tokenize-cache.md`

## Files changed

| Loop | File | Change |
|------|------|--------|
| L32a | `src/hestia/core/types.py` | Removed `TurnState`, `TERMINAL_STATES`, `ToolResult` |
| L32a | `tests/unit/test_core_types_dead_code_removed.py` | Regression guard |
| L32b | `src/hestia/context/builder.py` | Added `_PrefixLayer`, `_prefix_layers()`, removed kwargs |
| L32b | `src/hestia/orchestrator/engine.py` | Migrated one caller to `set_style_prefix` |
| L32b | `tests/unit/test_context_builder_prefix_registry.py` | 4 tests |
| L32c | `src/hestia/context/builder.py` | `_tokenize_cache`, `_count_tokens`, `_join_overhead` |
| L32c | `tests/unit/test_context_builder_tokenize_cache.py` | 4 tests |
| L32c | `docs/adr/ADR-0021-context-builder-prefix-registry-and-tokenize-cache.md` | ADR |

## Final gate

```
Tests:    712 passed, 6 skipped
Mypy:     0 errors
Ruff:     44 errors (no regression)
Version:  0.7.8
Branch:   feature/l32c-context-tokenize-cache
```

## Design notes for future loops

- The cache key is deliberately simple: `(role, content)`.  If a future loop
  adds images or multimodal content, the key will need to expand.
- `_join_overhead` is measured once per build.  A future optimisation could
  memoise it across builds, but the 2 extra `tokenize` calls are negligible
  compared to the O(N) savings in the loop.
- `ContextBuilder` still has no reactive invalidation.  If the inference
  client model changes mid-session, the orchestrator must construct a new
  builder.
