# L94 — Email Adapter Async Safety

**Status:** Spec only
**Branch:** `feature/l94-email-async-safety` (from `develop`)

## Intent

The email adapter (`src/hestia/email/adapter.py`) wraps synchronous `imaplib` and `smtplib` calls. While the email *tools* use `asyncio.to_thread` to avoid blocking the event loop, the `imap_session` context manager itself calls `conn.select(folder)`, `conn.close()`, and `conn.logout()` synchronously. These are I/O operations that can block the event loop for tens to hundreds of milliseconds (DNS resolution, TLS handshake on connection, server round-trips on close/logout).

For a single-user daemon this is tolerable. For Telegram/Matrix deployments handling concurrent users, a slow IMAP server blocks all other message processing during these calls. Wrapping them in `asyncio.to_thread` makes the adapter safe for concurrent use without changing the API surface.

## Scope

### §1 — Wrap blocking IMAP calls in `asyncio.to_thread`

In `src/hestia/email/adapter.py`, find the `imap_session` context manager (around line 62).

The following synchronous calls need wrapping:

1. `conn.select(folder)` (line ~78) — wrap in `await asyncio.to_thread(conn.select, folder)`
2. `conn.close()` (line ~86) — wrap in `await asyncio.to_thread(conn.close)`
3. `conn.logout()` (line ~91) — wrap in `await asyncio.to_thread(conn.logout)`

Also find `_imap_connect` (which creates the `imaplib.IMAP4_SSL` connection and calls `conn.login()`). If this method is synchronous and called from `imap_session`, wrap its call in `asyncio.to_thread` as well.

**Do NOT change the SMTP side.** The `_smtp_session` and `_smtp_connect` methods are called from email-sending tools that already use `asyncio.to_thread` at the tool level. Wrapping them again would be redundant.

**Import:** Add `import asyncio` at the top of the file if not already present.

**Commit:** `fix(email): wrap blocking IMAP calls in asyncio.to_thread`

### §2 — Add a comment explaining the async boundary

Add a module-level or class-level docstring note explaining the async strategy:

```python
# IMAP operations are wrapped in asyncio.to_thread because imaplib is
# synchronous. SMTP operations are NOT wrapped here because the email
# tools already run the entire send path in asyncio.to_thread.
```

This prevents a future contributor from either (a) wrapping SMTP calls redundantly or (b) removing the IMAP wrapping thinking it's unnecessary.

**Commit:** `docs(email): explain IMAP vs SMTP async boundary`

## Evaluation

- **Spec check:** All synchronous IMAP calls in `imap_session` (`select`, `close`, `logout`, and the connection/login in `_imap_connect`) are wrapped in `asyncio.to_thread`. SMTP calls are NOT wrapped (intentionally — the tools handle it).
- **Intent check:** The email adapter no longer blocks the event loop during IMAP operations. A slow IMAP server will not stall Telegram message processing. The comment explains why SMTP is treated differently, preventing future confusion.
- **Regression check:** `pytest tests/unit/ -q` green. `mypy src/hestia` clean. If there are email-related integration tests, they still pass. The API surface of `imap_session` is unchanged — callers still use `async with adapter.imap_session() as conn:`.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `grep -n "to_thread" src/hestia/email/adapter.py` shows wrapping on IMAP calls
- `.kimi-done` includes `LOOP=L94`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
