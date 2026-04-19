# L31 — orchestrator engine cleanup handoff

**Status:** complete
**Branch:** `feature/l31-engine-cleanup`
**Spec:** [`../development-process/kimi-loops/L31-engine-cleanup.md`](../development-process/kimi-loops/L31-engine-cleanup.md)

## What shipped

Pure refactor of `src/hestia/orchestrator/engine.py` (903 → 854 lines) with zero
behavior change.

| Extracted helper | Replaces | LOC saved |
| --- | --- | --- |
| `_build_failure_bundle(...)` | Duplicated failure-bundle bodies in `ContextTooLargeError` and generic `Exception` handlers | ~120 |
| `_check_confirmation(...)` | Duplicated confirmation gate in `call_tool` meta branch and direct-tool branch | ~40 |
| `ToolCallResult.error(content)` | 8× verbose `ToolCallResult(status="error", content=..., artifact_handle=None, truncated=False)` | ~30 |

Additional cleanups:
- `delegated` and `tool_chain` hoisted to the top of the outer `try` in
  `process_turn`; removed the `locals().get("delegated", False)` defensive
  idiom.
- Artifact handles are now accumulated directly from
  `ToolCallResult.artifact_handle` during dispatch; the regex-based
  `re.findall(r"artifact://...")` recovery path over stored messages is deleted.
- Single `get_messages` fetch per non-loop turn path (the post-DONE refetch is
  gone).

## Test results

```
701 passed, 6 skipped, 0 mypy errors
ruff: 44 errors in src/ (unchanged from L30 baseline)
```

The +10 tests are the three new regression modules:
- `test_orchestrator_failure_bundle.py`
- `test_orchestrator_confirmation_helper.py`
- `test_orchestrator_artifact_accumulation.py`

## Commits

1. `refactor(orchestrator): extract _build_failure_bundle helper`
2. `refactor(orchestrator): hoist delegated/tool_chain locals; drop locals().get`
3. `refactor(orchestrator): accumulate artifact handles from ToolCallResult`
4. `refactor(orchestrator): extract _check_confirmation helper`
5. `refactor(tools): add ToolCallResult.error classmethod`
6. `test(orchestrator): regression coverage for failure bundle, confirmation, artifacts`
7. `fix(orchestrator): resolve mypy and ruff regressions from refactor`
8. `chore(release): bump to 0.7.5`
9. `docs(handoff): L31 engine cleanup report`

## Carry-forward into L32

- Ruff baseline remains **44**. Any future loop touching `src/` must not
  regress this.
- `app.py` is still a 1,500+ line junk drawer of `_cmd_*` functions — queued
  for a future decomposition loop.
- `aiosqlite` `RuntimeError: Event loop is closed` warnings during test
  teardown are still present and unrelated.
