# Review Checklist

Run this checklist after every logical chunk of work, before advancing to the next chunk or declaring done.

## 1. §0 cleanup items

Verify each bullet in `## Review carry-forward` was addressed. If skipped intentionally, note why in a comment.

## 2. Config wiring

Every new field in `HestiaConfig` or a nested dataclass must be:
- Documented in the dataclass docstring
- Read by the CLI (`cli.py`), a platform adapter, or a runner
- Validated at load time if it has constraints
- Tested in at least one config test

## 3. Import breakage

When `__init__.py` exports change:
```bash
grep -r "from hestia.<module> import" tests/ src/
```
Check all test files that import from the modified package.

## 4. Migration/schema parity

If `schema.py` changed:
- Alembic migration exists under `migrations/versions/`
- Migration creates/drops the same tables/columns as schema.py
- `alembic upgrade head` + `alembic downgrade -1` works

## 5. Store-to-CLI wiring

If a store class gains a new public method:
- Check `cli.py` for the command that should expose it
- Check platform adapters (Telegram, Matrix) for the callback that should use it

## 6. In-memory state persistence

Any `dict` or `list` cache:
- Must have a database fallback if the data must survive restart
- Must be documented if it's intentionally ephemeral

## 7. Test coverage

- New behavior has at least one test
- Edge cases are covered (empty input, max size, error paths)
- Existing tests still pass

## 8. Type safety

- `mypy src/hestia` reports 0 errors
- New functions have type annotations
- `Any` is avoided unless truly necessary

## 9. Async safety

No synchronous I/O inside `async def`:
- File I/O → `asyncio.to_thread` or `aiofiles`
- Subprocess → `asyncio.create_subprocess_exec`
- HTTP → `httpx.AsyncClient` or `aiohttp`
- SQLite → `aiosqlite`

## 10. Exception hygiene

- No bare `except:` — narrow to specific types
- Unexpected exceptions are logged at `ERROR` before re-raise
- Custom exceptions inherit from `HestiaError`

## 11. Security

- Dangerous tools require confirmation callback
- Path sandboxing respects `allowed_roots`
- No secrets in source code
- `http_get` blocks private IPs

## 12. Documentation

- New CLI commands appear in README CLI reference
- New config options appear in README config section
- ADR written for architectural decisions
