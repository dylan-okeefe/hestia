# L70 — Memory Search Scope & Concurrent Tool Safety

## Intent & Meaning

This loop fixes two medium-severity issues flagged in the April 22 code review (M2 and M3) that create silent failures and cascading cancellation:

1. **M2 — Partial identity context leaks isolation.** When `memory.search()`, `list_memories()`, `delete()`, or `count()` was called with exactly one of `platform`/`platform_user` set (e.g., `platform="cli"` but `platform_user=None`), the code fell through to an *unscoped* query, returning every user's memories. This is the opposite of fail-closed.

2. **M3 — Concurrent tool exceptions kill siblings.** `TurnExecution._execute_tool_calls` used `asyncio.gather` without `return_exceptions=True`. If one concurrent tool raised (e.g., confirmation callback threw, or a registry race occurred), the exception cancelled all in-flight sibling tools and failed the entire turn.

## Changes Made

### `src/hestia/memory/store.py`

- **`_resolve_scope`**: Added a partial-scope guard after ContextVar fallback. If exactly one of `platform`/`platform_user` is `None` after resolution, log a warning and normalize both to `None`. This prevents the isolation leak in all query methods (`search`, `list_memories`, `delete`, `count`) and makes `save()` safer too.

```python
if (platform is None) != (platform_user is None):
    logger.warning(
        "Partial identity context (platform=%r, platform_user=%r); "
        "treating as unscoped to avoid isolation leak",
        platform,
        platform_user,
    )
    platform = None
    platform_user = None
```

### `src/hestia/orchestrator/execution.py`

- **`_execute_tool_calls`**: Wrapped the body of `_run_one` (the inner function dispatched by `asyncio.gather`) in `try/except`. On exception, returns `ToolCallResult.error(...)` with the exception type name, so the gather completes normally and sibling tools are not cancelled.

```python
async def _run_one(idx: int) -> tuple[int, ToolCallResult]:
    tc = tool_calls[idx]
    try:
        result = await self._dispatch_tool_call(session, tc, allowed_tools)
    except Exception as exc:
        logger.exception("Tool call %s failed during concurrent dispatch", tc.name)
        result = ToolCallResult.error(
            f"Tool {tc.name} failed: {exc}", error_type=type(exc).__name__
        )
    return idx, result
```

### Tests

- **`tests/unit/test_memory_user_scope.py`**:
  - `test_save_partial_identity_context_warns_and_unscopes`
  - `test_search_partial_identity_context_warns_and_unscopes`

- **`tests/unit/test_orchestrator_concurrent_tools.py`**:
  - `test_concurrent_tool_exception_does_not_kill_siblings` — three concurrent tools, middle one raises `RuntimeError`; asserts all three complete and the error is materialized as a tool result message.

## Verification

- `pytest tests/unit/ tests/integration/ -q` → **1062 passed, 6 skipped**
- `ruff check src/hestia/memory/store.py src/hestia/orchestrator/execution.py tests/unit/test_memory_user_scope.py tests/unit/test_orchestrator_concurrent_tools.py` → **all checks passed**
- `mypy src/hestia/memory/store.py src/hestia/orchestrator/execution.py --no-incremental` → **no issues**

## Commit

```
fix(memory,orchestrator): fail-loud on partial identity scope and shield concurrent tools
```

## Risks & Follow-ups

- **None.** Both fixes are strictly safer than the prior behavior. No interface changes.
- The partial-scope guard in `_resolve_scope` now also affects `save()` — if a caller passes exactly one of platform/platform_user, the row is saved as unscoped with a warning. This is safer than saving with a partial key that scoped queries would never match.
