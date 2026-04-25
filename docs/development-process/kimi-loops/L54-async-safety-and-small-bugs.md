# L54 — Async Safety & Small Bugs

**Status:** Spec only. Pre-release hotfix arc — **merge to `develop`.**

**Branch:** `feature/l54-async-safety-and-small-bugs` (from `develop`)

## Goal

Fix all blocking-sync-in-async bugs and small code-quality issues identified in
the v0.10.0 pre-release evaluation. These are low-risk, high-correctness fixes
that should land before the next release tag.

## Scope

### §1 — Blocking socket.getaddrinfo() in async transport

**File:** `src/hestia/tools/builtin/http_get.py`  
**Lines:** ~54 (inside `SSRFSafeTransport.handle_async_request()`)

`socket.getaddrinfo()` is a synchronous, potentially slow syscall called inside
an async method on the event loop. Replace with:

```python
# Before
addr_info = socket.getaddrinfo(hostname, None)

# After
loop = asyncio.get_running_loop()
addr_info = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
```

Add a test that mocks `asyncio.to_thread` to verify the call path.

### §2 — Sync file I/O in read_file / write_file / list_dir

**Files:**
- `src/hestia/tools/builtin/read_file.py` — `p.read_bytes()`
- `src/hestia/tools/builtin/write_file.py` — `target.write_text()`
- `src/hestia/tools/builtin/list_dir.py` — `p.iterdir()`, `p.stat()`

Wrap all sync filesystem calls in `asyncio.to_thread()`. Follow the pattern
already used in `ArtifactStore.store()`:

```python
content = await asyncio.to_thread(p.read_bytes)
```

**Note:** `list_dir` may need to thread the whole iteration loop, or use
`pathlib.Path` methods inside `to_thread`.

Add/update tests to ensure the tools still work (mock `asyncio.to_thread` if
necessary).

### §3 — Duplicate artifact_refs assignment

**File:** `src/hestia/tools/builtin/delegate_task.py`  
**Lines:** 177 & 184

Line 177 assigns `artifact_refs = list(turn.artifact_handles)`. Line 184
re-assigns with a type annotation, overwriting. Delete line 184 (the annotated
re-assignment). Keep the comment block that explains why the list copy exists.

### §4 — TimeoutError vs asyncio.TimeoutError

**File:** `src/hestia/tools/builtin/delegate_task.py`

The `except` clause catching `TimeoutError` from `asyncio.wait_for` should use
`asyncio.TimeoutError` explicitly for clarity:

```python
# Before
except TimeoutError:

# After
except asyncio.TimeoutError:
```

### §5 — Lazy timedelta import inside hot path

**File:** `src/hestia/orchestrator/engine.py`  
**Line:** ~279

`from datetime import timedelta` is imported inside `_prepare_turn_context`,
which runs on every turn. Hoist to the top of the file where `datetime` is
already imported.

### §6 — WebSearchError should inherit HestiaError

**File:** `src/hestia/tools/builtin/web_search.py`

`WebSearchError` currently inherits `RuntimeError`. It should inherit
`HestiaError` so `classify_error()` dispatches it correctly and failure
analytics bucket it as a web-search failure rather than "UNKNOWN".

```python
from hestia.core.errors import HestiaError

class WebSearchError(HestiaError):
    ...
```

Add a test in `tests/unit/test_web_search.py` verifying `classify_error` maps
it correctly.

### §7 — ScheduledTask invariant enforcement

**File:** `src/hestia/core/types.py`

`ScheduledTask` has a comment "Exactly one of cron_expression or fire_at must
be set" but no enforcement. Add a `__post_init__` validator:

```python
def __post_init__(self):
    if bool(self.cron_expression) == bool(self.fire_at):
        raise ValueError("Exactly one of cron_expression or fire_at must be set")
```

Add a test in `tests/unit/` (or extend existing scheduler type tests).

### §8 — Remove dead **kw: Any from file tool factories

**Files:**
- `src/hestia/tools/builtin/read_file.py` — `make_read_file_tool(**kw: Any)`
- `src/hestia/tools/builtin/write_file.py` — `make_write_file_tool(**kw: Any)`
- `src/hestia/tools/builtin/list_dir.py` — `make_list_dir_tool(**kw: Any)`

The `**kw` arguments are silently dropped. Remove them from signatures and all
call sites.

### §9 — Remove legacy string-match fallback in classify_error

**File:** `src/hestia/orchestrator/errors.py`

The bottom of `classify_error()` has a string-match fallback for "max
iterations" kept for "legacy call sites". All raises have been updated to use
`MaxIterationsError`. Remove the fallback and the comment documenting it.

### §10 — Move ContextVar definitions to runtime_context.py

**File:** `src/hestia/tools/builtin/memory_tools.py`

`current_session_id` and `current_trace_store` are defined in
`memory_tools.py` but imported by `http_get.py` and `web_search.py`. This is a
weird cross-tool dependency.

Move both ContextVar definitions to `src/hestia/runtime_context.py` (create it
if it doesn't exist). Update:
- `memory_tools.py` to import from `runtime_context`
- `http_get.py` to import from `runtime_context`
- `web_search.py` to import from `runtime_context`
- Any other files that reference them

Keep `runtime_context.py` as the single source of truth for all runtime
ContextVars (including `scheduler_tick_active`, `current_platform`,
`current_platform_user` which already live in `runtime_context.py` or
`platforms/runners.py`).

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

All three must pass. If ruff has pre-existing baseline issues, note the count
and ensure no new issues were introduced.

## Acceptance

- `socket.getaddrinfo` is called via `asyncio.to_thread` in http_get.
- `read_file`, `write_file`, `list_dir` use `asyncio.to_thread` for sync I/O.
- `delegate_task.py` has no duplicate assignment.
- `delegate_task.py` catches `asyncio.TimeoutError`.
- `engine.py` imports `timedelta` at module level.
- `WebSearchError` inherits `HestiaError`.
- `ScheduledTask` validates exactly-one-of constraint.
- File tool factories have no `**kw: Any`.
- `classify_error` has no legacy fallback.
- ContextVars live in `runtime_context.py`.

## Handoff

- Write `docs/handoffs/L54-async-safety-and-small-bugs-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l54-async-safety-and-small-bugs` to `develop`.
- Advance `KIMI_CURRENT.md` to L55.

## Dependencies

None. Can start immediately from `develop` tip.
