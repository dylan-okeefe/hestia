# L238 — Scope-aware memory maintenance (Loop B) handoff

**Status:** Ready for Cursor review / human-gated merge.  
**Branch:** `feature/l238-scope-aware-memory-maintenance`  
**Scope:** Spec Loop B and decisions §9 of `docs/reviews/decisions-thread-scoped-memory.md`.

## Outcome

Extended the ADR-049 memory maintenance subsystem to respect the two-tier
global/topic memory scope introduced in Loop A. Dedupe and supersession now
operate within scope, the protected set is evaluated per scope, and undo
restores only the scope-specific losers of a maintenance action. The deferred
scope-promotion pass (topic → global) is explicitly left for a future
Proposals-gated loop.

## Commits on branch

1. `feat(memory): scope-aware deduplication in maintenance`
2. `feat(memory): scope-aware supersession and protected sets`
3. `feat(memory): per-scope retention and undo`
4. `test(memory): add scope-aware maintenance tests`

## Per-item accounting

| Spec / decision item | Implementation | Verification |
| --- | --- | --- |
| Scope-aware deduplication: identical content in different scopes is not merged | `DeterministicDeduper` and `LLMDeduper` compute a scope key (global or sorted topic IDs) for every active memory; exact and FTS-overlap merges are scoped to the same key. | `test_scope_aware_maintenance.py::TestScopeAwareDeterministicDedupe` |
| Global duplicate is merged | Global memories share the `__global__` scope key. | `test_within_global_duplicate_is_merged` |
| Topic duplicate is merged | Topic-scoped memories with the same topic set share a scope key. | `test_within_topic_duplicate_is_merged` |
| Global/topic identical content stays separate | Different scope keys prevent grouping. | `test_global_and_topic_identical_content_are_not_merged` |
| Scope-aware supersession | `ContradictionResolver` only generates and judges pairs whose scope keys match. | `test_supersession_does_not_cross_scopes`, `test_within_topic_supersession_replaces_older_fact` |
| Protected set is per scope | Protected memories are still skipped individually; because dedupe groups by scope, a protected global cannot block topic-scope deduplication. | `test_protected_global_does_not_block_topic_dedupe` |
| Undo is scope-aware | `MaintenanceUndo` restores the specific loser memory IDs recorded in a trace action; undoing a topic-scope merge does not restore a global-scope merge. | `test_undo_of_scoped_action_does_not_affect_other_scopes` |
| Deferred scope-promotion pass | Left for a future loop; recorded as a TODO in `src/hestia/memory/maintenance/service.py`. | N/A |

## Files changed

- `src/hestia/memory/maintenance/scopes.py` — new scope-key helpers (`memory_scope_key`, `format_scope_key`).
- `src/hestia/memory/store.py` — added `get_topic_ids_for_memories()` batch lookup.
- `src/hestia/memory/maintenance/dedupe.py` — exact and FTS-overlap dedupe now grouped/judged per scope; trace details include scope.
- `src/hestia/memory/maintenance/llm_dedupe.py` — candidate pair generation and merge judging filtered to same scope; trace details include scope.
- `src/hestia/memory/maintenance/contradictions.py` — contradiction pairs filtered to same scope; trace details include scope.
- `src/hestia/memory/maintenance/undo.py` — undo action carries forward the original scope from trace details for audit.
- `src/hestia/memory/maintenance/service.py` — added TODO documenting the deferred scope-promotion pass.
- `tests/unit/memory/maintenance/test_scope_aware_maintenance.py` — new scope-aware maintenance tests.

## Quality gates

```bash
uv run pytest tests/unit/memory/maintenance/ tests/unit/memory/test_topic_scoped_memory.py tests/unit/test_memory_tools.py -q
# 68 passed

uv run ruff check src/hestia/memory/maintenance/ tests/unit/memory/maintenance/
# clean

uv run mypy src/hestia/memory/maintenance/
# clean

uv run ruff check src/hestia/memory/store.py && uv run mypy src/hestia/memory/store.py
# clean
```

Full-repo `ruff`/`mypy` still report pre-existing issues in untouched files.

## Deferred / not in this loop

- Scope-promotion pass (topic → global): explicitly deferred to a future
  Proposals-gated loop with optional ultra-high-confidence auto-promote + digest
  + undo, per decisions §9.
- Loop C: memory UI redesign.

## Next

1. Dylan/Cursor review.
2. If approved, merge `feature/l238-scope-aware-memory-maintenance` into
   `develop` and push.
3. After L238 lands, schedule the scope-promotion pass as a new loop/Proposal.
