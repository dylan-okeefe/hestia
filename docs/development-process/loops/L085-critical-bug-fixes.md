# L85 — Critical Bug Fixes (April 29 Code Review)

**Status:** In progress  
**Branch:** `feature/l85-april-29-critical-fixes` (from `develop`)  
**Scope:** Two must-fix bugs from the April 29 code review. Tiny surface area, high impact.

---

## Items

| ID | Issue | File | Fix |
|----|-------|------|-----|
| C1 | `AppContext.close()` never closes inference client | `src/hestia/app.py` | Use `'inference' in self.__dict__` instead of `hasattr(self, '_inference')` |
| C2 | `ToolExecutionError` missing from `classify_error` | `src/hestia/errors.py` | Add mapping entry |
| C3 | Missing test for C2 | `tests/unit/test_failure_tracking.py` | Add `test_classify_tool_execution_error` |

---

## C1 Detail: `AppContext.close()` resource leak

Current code (line 256–261):

```python
async def close(self) -> None:
    """Close lazily-created resources."""
    if hasattr(self, '_inference') and self._inference is not None:
        await self._inference.close()
    if self.email_adapter is not None:
        self.email_adapter.close()
```

`inference` is a `functools.cached_property`. The cached value lives in `self.__dict__['inference']`, not `_inference`. `hasattr(self, '_inference')` is always `False`, so the inference client's `httpx.AsyncClient` is never closed.

Fix:
```python
async def close(self) -> None:
    if 'inference' in self.__dict__:
        await self.inference.close()
    if self.email_adapter is not None:
        self.email_adapter.close()
```

**Critical rule:** Use `'inference' in self.__dict__` to check whether a `functools.cached_property` has been materialized. Do NOT use `hasattr()` — it triggers the descriptor and creates the resource.

## C2 Detail: `classify_error` mapping gap

`classify_error` in `src/hestia/errors.py` maps exception types to `(FailureClass, severity)`. `ToolExecutionError` is absent. Tool failures record `failure_class="unknown"` instead of `failure_class="tool_error"`.

Add one line to the mapping dict:
```python
ToolExecutionError: (FailureClass.TOOL_ERROR, "medium"),
```

`ToolExecutionError` is already imported at the top of `errors.py` (it's defined in the same file).

## C3 Detail: Test coverage

Add to `TestClassifyError` in `tests/unit/test_failure_tracking.py`:

```python
def test_classify_tool_execution_error(self):
    """ToolExecutionError maps to TOOL_ERROR."""
    exc = ToolExecutionError("test_tool", ValueError("boom"))
    fc, severity = classify_error(exc)
    assert fc == FailureClass.TOOL_ERROR
    assert severity == "medium"
```

Import `ToolExecutionError` in the file's import block.

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

All three must pass.

## Acceptance

- `pytest` green
- `mypy` 0 errors in changed files
- `ruff` at baseline or better
- `.kimi-done` includes `LOOP=L85`

## Handoff

- Write `docs/handoffs/L85-april-29-critical-fixes-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
