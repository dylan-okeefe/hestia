# Kimi loop L33b — `EmailAdapter` per-invocation IMAP session reuse

## Hard step budget

≤ **5 commits**, ≤ **2 new test modules**, no exploration outside `src/hestia/email/`, the email tool module, and tests. Stop after handoff commit; write `.kimi-done`; push; exit.

## Review carry-forward

From L33a (merged at `<TBD>`):

- Test baseline: **<TBD>**.
- Mypy 0. Ruff ≤ 44.

From the external code-quality review:

- `EmailAdapter` opens a fresh `IMAP4_SSL` connection (TLS handshake + IMAP `LOGIN` + `SELECT`) for **every** operation: `list_messages`, `read_message`, `search_messages`, `create_draft`, `send_draft`, `move_message`, `flag_message`. A single `email_list` + `email_read` round trip is **2 TLS handshakes + 2 logins**. ~300–500 ms per call. Many providers rate-limit aggressive reconnects.

**Branch:** `feature/l33b-email-session-reuse` from `develop` post-L33a.

**Target version:** **0.7.10** (patch — perf + new composite tool).

---

## Scope

### §1 — Add `imap_session()` async context manager to `EmailAdapter`

In `src/hestia/email/adapter.py`:

- Add `async def imap_session(self, *, folder: str = "INBOX") -> AsyncContextManager[imaplib.IMAP4_SSL]` (or whatever the existing connection abstraction returns) that:
  - Calls the existing `_imap_connect()` (or equivalent) **once** on entry.
  - Calls `SELECT folder` once on entry.
  - Calls `conn.logout()` on exit, even if the body raises.
- Refactor the existing per-method connection blocks (`list_messages`, `read_message`, `search_messages`, `create_draft`, `move_message`, `flag_message`) so the **per-method** behavior is unchanged: each still opens and closes its own session via `async with self.imap_session(folder=...):`. **Crucially**, when called inside an outer `async with self.imap_session():`, the inner methods detect the active session and reuse it rather than nesting.
- Implementation hint: track the active session on a `contextvars.ContextVar[IMAP4_SSL | None]` so reuse is automatic for code running inside the outer `async with`. Outer enters → ContextVar set; inner methods check ContextVar; outer exits → ContextVar reset and `logout()` called.

### §2 — New composite tool `email_search_and_read`

In whichever module hosts the email tools (`src/hestia/tools/builtin/email_tools.py` or similar):

- New tool factory `make_email_search_and_read_tool(adapter: EmailAdapter) -> Tool` that:
  - Takes `query: str` and `limit: int = 5`.
  - Inside one `async with adapter.imap_session()`: runs the search, then reads the top `limit` messages, returning a list of dicts (uid, from, subject, snippet of body, full body in artifact handle if > N bytes).
  - Single round trip in IMAP terms (one connection, one login, one SELECT).
- Register the new tool in `src/hestia/app.py` alongside the existing email tools.

### §3 — `SMTP` short-lived send remains unchanged

Out of scope for L33b. `send_draft` still opens its own SMTP connection per call — IMAP and SMTP are separate sessions. Document this in the new tool's docstring.

### §4 — Tests

`tests/unit/test_email_session_reuse.py`:

- `test_session_uses_single_connection` — patch `IMAP4_SSL` with a counting mock; inside one `async with adapter.imap_session():` call `list_messages` and `read_message` back to back; assert `IMAP4_SSL.__init__` called **exactly once** and `logout()` called **exactly once**.
- `test_session_closes_on_exception` — body of `async with` raises; assert `logout()` still called.
- `test_nested_session_reuses_outer` — two `async with imap_session():` blocks (outer + inner) ⇒ one connection total.
- `test_no_outer_session_each_method_opens_own` — call `list_messages` twice without an outer `async with` ⇒ two connections (existing behavior preserved).

`tests/integration/test_email_search_and_read.py`:

- Use the existing email mock fixture (or `aioimaplib`-based stub) to exercise the new tool end-to-end. Assert: search returns ids, each id is then read, response shape matches the documented dict layout.

### §5 — Version bump + CHANGELOG

- `pyproject.toml` → `0.7.10`.
- `uv lock`.
- CHANGELOG entry under `[0.7.10] — 2026-04-18`. Note: per-invocation reuse pattern, new `email_search_and_read` tool, SMTP unchanged.
- No ADR (engineering polish — the new context manager and composite tool are obvious extensions of the existing surface).

---

## Commits (5 total)

1. `perf(email): add imap_session() async context manager with ContextVar-based reuse`
2. `refactor(email): route every per-method connection through imap_session()`
3. `feat(email): new email_search_and_read tool composing search + per-id read`
4. `test(email): session reuse and composite-tool regression coverage`
5. `chore(release): bump to 0.7.10`

---

## Required commands

```bash
uv lock
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/
```

Mypy 0. Ruff ≤ 44.

---

## `.kimi-done` contract

```
HESTIA_KIMI_DONE=1
LOOP=L33b
BRANCH=feature/l33b-email-session-reuse
COMMIT=<final commit sha>
TESTS=<pytest summary>
MYPY_FINAL_ERRORS=<count>
```

---

## Critical Rules Recap

- Backward-compatible: every existing email tool behaves identically when called outside an `async with imap_session()`.
- ContextVar reuse must NOT leak across asyncio tasks — verify with the nested-session test.
- SMTP send is out of scope. Do not refactor it.
- Push and stop.
