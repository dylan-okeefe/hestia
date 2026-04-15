# Hestia L15 Handoff Report — Security & Bug Fixes

**Date:** 2026-04-15  
**Loop:** L15  
**Branch:** `feature/l15-security-hardening`  
**Final Commit:** `d5a57f8c7e0871a99e3f58609f4992939ea9c74b`

---

## Summary

All five security and bug-fix sections from the L15 spec have been implemented, tested, and committed. The branch is ready for review/merge into `develop`.

---

## §1 — SSRF Protection for `http_get`

**Files changed:**
- `src/hestia/tools/builtin/http_get.py`
- `tests/unit/test_http_get_ssrf.py`
- `tests/unit/test_builtin_tools_new.py`

**Changes:**
- Introduced `SSRFSafeTransport`, a custom `httpx.AsyncBaseTransport` that resolves hostnames and validates IPs **at connection time** (not request time).
- This blocks both redirect-based SSRF and DNS-rebinding attacks.
- Kept `_is_url_safe()` as a fast pre-flight check for user-friendly errors (scheme/hostname validation only), but removed its DNS resolution logic.
- Added `0.0.0.0/8` to the blocked IP ranges.

**Tests:**
- `test_ssrf_redirect_blocked` — verifies 302 redirect to `169.254.169.254` is blocked.
- `test_ssrf_dns_rebinding_blocked` — mocks DNS to return a private IP at transport time.
- `test_ssrf_transport_blocks_private_ip` — direct transport tests for blocked ranges.
- Updated pre-flight tests to reflect the new `_is_url_safe()` behavior.

---

## §2 — Terminal Tool Process Group Kill

**Files changed:**
- `src/hestia/tools/builtin/terminal.py`
- `tests/unit/test_terminal.py`

**Changes:**
- Added `start_new_session=True` to `asyncio.create_subprocess_shell()` so the shell and its children run in a dedicated process group.
- On timeout, `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` kills the entire process group.
- Kept `PermissionError` / `ProcessLookupError` fallbacks.
- Removed stale `Phase 1c will enforce this` comment.

**Tests:**
- `test_timeout_kills_process_group` — spawns a child process, triggers timeout, asserts both parent and child PIDs are dead.
- `test_timeout_returns_timeout_message` — verifies the timeout string is returned.

---

## §3 — Remove `NameError` Guards in `engine.py`

**Files changed:**
- `src/hestia/orchestrator/engine.py`

**Changes:**
- Initialized `allowed_tools`, `policy_snapshot`, and `slot_snapshot` at the top of `process_turn()` before the main `try` block.
- Removed both `except NameError:` handlers.
- Preserved the `except (TypeError, AttributeError)` handler for slot snapshot serialization.

**Tests:**
- Existing orchestrator tests continue to pass; no new tests required.

---

## §4 — Atomic Write for `ArtifactStore` Inline Index

**Files changed:**
- `src/hestia/artifacts/store.py`
- `tests/unit/test_artifacts.py`

**Changes:**
- `_save_inline_index()` now writes to a temp file (`tempfile.mkstemp`) and atomically replaces `inline.json` via `os.replace()`.
- On any exception during write, the temp file is unlinked and the original index is preserved.

**Tests:**
- `test_inline_index_atomic_write` — verifies saved index is valid JSON.
- `test_inline_index_survives_crash` — mocks `json.dump` to raise mid-write and asserts the original `inline.json` is uncorrupted.

---

## §5 — Empty `allowed_users` Denies All (Telegram)

**Files changed:**
- `src/hestia/platforms/telegram_adapter.py`
- `src/hestia/config.py`
- `tests/unit/test_telegram_adapter.py`

**Changes:**
- Changed `_is_allowed()` to return `False` when `allowed_users` is empty.
- Updated `TelegramConfig.allowed_users` docstring to clarify: "Empty list denies all users. Populate with user IDs or usernames to allow access."
- Verified `MatrixConfig`/`MatrixAdapter` already has the correct deny-all behavior for `allowed_rooms`.

**Tests:**
- `test_empty_allowed_users_denies_all` — asserts `False` when `allowed_users=[]`.
- Updated existing tests (`test_handle_start_sends_welcome`, `test_handle_message_calls_on_message_callback`) to explicitly set allowed users so they continue to pass.

---

## Test Results

```
$ uv run pytest tests/unit/ tests/integration/ -q
472 passed, 6 skipped
```

Ruff check shows no new violations in changed files (pre-existing warnings in other files are noted but out of scope).

---

## Next Steps

1. Merge `feature/l15-security-hardening` into `develop`.
2. Proceed to **L16** (`docs/orchestration/kimi-loops/L16-pre-public-cleanup.md`).
