# L189 — Backend Quality & Performance

**Status:** Spec only  
**Branch:** `feature/l189-backend-quality-and-performance` (from `develop`)  
**Depends on:** L178 (error dashboard), L180 (authorization)

## Intent

Two backend quality issues surfaced in review: loose typing on memory helpers and sequential I/O in the error dashboard aggregation. This loop tightens both.

## Scope

### §1 — Type `_memory_to_dict` parameter

**Why:** `memory.py` line 16 takes `mem: Any`, defeating type checking on memory object access.

**In `src/hestia/web/routes/memory.py`:**

- Import the actual `Memory` model type from persistence
- Change `_memory_to_dict(mem: Any)` to `_memory_to_dict(mem: Memory)`
- Fix any type errors that surface (e.g., attribute access, optional fields)
- Check `config.py` routes for similar `dict[str, Any]` returns — tighten where straightforward

**Commit:** `refactor(web): type _memory_to_dict parameter with Memory model`

---

### §2 — Parallelize error dashboard aggregation

**Why:** `list_errors` makes 5+ sequential `await` calls. Independent fetches should run concurrently.

**In `src/hestia/web/routes/errors.py`:**

- Identify which fetches are independent (e.g., `list_failed`, `list_workflows`, `list_tasks_with_errors`)
- Wrap independent calls in `asyncio.gather()`
- Keep dependent calls sequential (e.g., session batch lookups that need IDs from prior results)
- Add a brief comment explaining the dependency chain

Before:
```python
failed = await list_failed(50)
workflows = await list_workflows()
tasks = await list_tasks_with_errors(50)
# ... etc
```

After:
```python
failed, workflows, tasks = await asyncio.gather(
    list_failed(50),
    list_workflows(),
    list_tasks_with_errors(50),
)
```

**Commit:** `perf(web): parallelize independent fetches in error dashboard`

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

All three must pass.

## Handoff

- Verify `mypy` reports 0 errors in `memory.py`
- Verify error dashboard still returns identical data after parallelization
