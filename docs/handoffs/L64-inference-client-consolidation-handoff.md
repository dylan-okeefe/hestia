# L64 — InferenceClient Consolidation & Resource Lifecycle Handoff

**Branch:** `feature/l64-inference-client-consolidation`
**Status:** Complete, ready for review

## Changes

### §1 — Extract `_request()` helper
- Added `InferenceClient._request()` that wraps HTTP calls and translates `httpx` exceptions to `HestiaError` subclasses
- `health()`, `tokenize()`, `chat()`, `slot_save()`, `slot_restore()`, `slot_erase()` all route through `_request()`
- Zero `except httpx.` blocks remain outside `_request()`

### §2 — Context-manager support
- Added `__aenter__`/`__aexit__` to `InferenceClient`

### §3 — Wire lifecycle into app.py
- Added `CoreAppContext.close()` and `CliAppContext.close()`
- `chat`, `ask`, and `scheduler` shutdown paths now call `await app.close()`

### §4 — EmailAdapter connection lifecycle
- Added `_smtp_session()` context manager to `EmailAdapter`
- `send_draft` now uses `with self._smtp_session()` instead of manual try/finally

## Quality gates

- `pytest tests/unit/test_inference_client.py` — 2 passed
- `mypy src/hestia/core/inference.py src/hestia/email/adapter.py src/hestia/app.py src/hestia/commands/chat.py src/hestia/commands/scheduler.py` — no issues
- `ruff check` — clean

## Intent verification

- **One place to change error handling:** Verified by grep — zero `except httpx.` outside `_request()`.
- **Shutdown is obvious:** `app.close()` is called in chat, ask, and scheduler shutdown paths.
- **SMTP is as clean as IMAP:** Both now use context managers for connection lifecycle.

## Next

Ready to merge to `develop` and start L65.
