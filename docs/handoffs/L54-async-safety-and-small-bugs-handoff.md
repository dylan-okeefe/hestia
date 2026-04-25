# L54 — Async Safety & Small Bugs

## Scope

Fix all blocking-sync-in-async bugs and small code-quality issues identified in
the v0.10.0 pre-release evaluation. Low-risk, high-correctness fixes.

## Commits

| Commit | Section | Description |
|--------|---------|-------------|
| `3167dcd` | §1 | `socket.getaddrinfo()` → `asyncio.to_thread()` in `SSRFSafeTransport` |
| `2f77b32` | §2 | `read_file` / `write_file` / `list_dir` → `asyncio.to_thread()` for sync I/O |
| `4ed2c77` | §3 & §4 | Remove duplicate `artifact_refs`; catch `asyncio.TimeoutError` |
| `28f9bfd` | §5 | Hoist `timedelta` import to module level in `engine.py` |
| `826d6b6` | §6 | `WebSearchError` inherits `HestiaError`; `classify_error` maps to `TOOL_ERROR` |
| `218aab8` | §7 | `ScheduledTask.__post_init__` enforces mutual exclusion of `cron_expression` / `fire_at` |
| `3954c44` | §8 | Remove dead `**kw: Any` from file tool factories |
| `cafded6` | §9 | Remove legacy string-match fallback in `classify_error` |
| `e8c7e82` | §10 | Move `current_session_id` / `current_trace_store` to `runtime_context.py` |

## Files changed

- `src/hestia/tools/builtin/http_get.py` — async SSRF check, updated description
- `src/hestia/tools/builtin/read_file.py` — `asyncio.to_thread` wrapper
- `src/hestia/tools/builtin/write_file.py` — `asyncio.to_thread` wrapper
- `src/hestia/tools/builtin/list_dir.py` — `asyncio.to_thread` wrapper
- `src/hestia/tools/builtin/delegate_task.py` — deduplicate assignment, `asyncio.TimeoutError`
- `src/hestia/orchestrator/engine.py` — hoist `timedelta`, import ContextVars from `runtime_context`
- `src/hestia/tools/builtin/web_search.py` — `WebSearchError(HestiaError)`
- `src/hestia/errors.py` — remove legacy fallback, add `WebSearchError` mapping
- `src/hestia/core/types.py` — `ScheduledTask.__post_init__`
- `src/hestia/tools/builtin/memory_tools.py` — ContextVars imported from `runtime_context`
- `src/hestia/runtime_context.py` — new ContextVar definitions
- `src/hestia/tools/builtin/__init__.py` — updated exports
- `tests/unit/test_web_search.py` — `classify_error` mapping test
- `tests/unit/test_scheduler_store.py` — still passes with mutual-exclusion validator
- `tests/integration/test_egress_audit.py` — updated imports
- `tests/unit/test_memory_tools.py` — updated imports

## Quality gates

- **Tests:** 142 passed (targeted subset), full unit suite green.
- **Mypy:** 0 new errors in changed files (2 pre-existing in unchanged files).
- **Ruff:** 0 new issues introduced; baseline unchanged.

## Notes

- `ScheduledTask.__post_init__` was changed from "exactly one of" to "mutual
  exclusion" during review because database deserialization creates tasks with
  both fields `None` before they are populated.
- The `list_dir` `asyncio.to_thread` wrapper threads the whole `iterdir()`
  iteration loop to avoid multiple synchronous syscalls on the event loop.

## Merge status

Merged to `develop` via `feature/l54-async-safety-and-small-bugs`.
