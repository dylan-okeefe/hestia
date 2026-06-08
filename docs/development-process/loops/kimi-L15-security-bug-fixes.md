# Kimi loop L15 — Security & bug fixes (pre-public hardening)

## Review carry-forward

- Pre-existing aiosqlite thread warnings in pytest — housekeeping, not blocking.
- `feature/typing-indicator-ux` just merged: orchestrator now uses typing indicators instead of "Thinking..." messages. No carry-forward bugs from that change.

**Branch:** `feature/l15-security-hardening` from **`develop`**.

---

## Goal

Fix all security vulnerabilities and real bugs identified in the pre-public code review. Every section includes tests.

---

## §-1 — Create branch

```bash
git checkout develop
git pull origin develop
git checkout -b feature/l15-security-hardening
```

---

## §1 — Fix http_get SSRF: redirect validation + DNS rebinding

**File:** `src/hestia/tools/builtin/http_get.py`

### Problem 1: Redirect SSRF
`follow_redirects=True` is set, but only the **initial** URL is validated. A redirect chain could land on `http://169.254.169.254/` (cloud metadata) and bypass the SSRF check.

### Problem 2: DNS rebinding (TOCTOU)
`_is_url_safe()` resolves DNS via `socket.getaddrinfo()`, but then `httpx` opens a **new** socket with a separate DNS lookup. An attacker controlling DNS with TTL=0 could rebind between the two calls.

### Fix

Replace the pre-flight DNS check + `httpx.AsyncClient(follow_redirects=True)` with a **custom `httpx.AsyncBaseTransport`** that intercepts **every** connection attempt (initial + redirects) and validates the resolved IP before connecting.

**Implementation sketch:**

```python
import ipaddress
import socket
import httpx

_BLOCKED_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Transport that validates every connection target against blocked IP ranges.

    Prevents both redirect-based SSRF and DNS rebinding attacks by checking
    the resolved IP at connection time, not at request time.
    """

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        if hostname:
            # Resolve at connection time — same lookup httpx will use
            try:
                addr_info = socket.getaddrinfo(str(hostname), None)
            except socket.gaierror as exc:
                raise httpx.ConnectError(f"Cannot resolve hostname: {hostname}") from exc

            for _family, _, _, _, sockaddr in addr_info:
                ip = ipaddress.ip_address(sockaddr[0])
                for blocked in _BLOCKED_RANGES:
                    if ip in blocked:
                        raise httpx.ConnectError(
                            f"SSRF blocked: {hostname} resolves to {ip} (in {blocked})"
                        )

        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()
```

Then use this transport in the fetch function:

```python
async with httpx.AsyncClient(
    transport=SSRFSafeTransport(),
    follow_redirects=True,
    timeout=timeout_seconds,
) as client:
    response = await client.get(url)
```

Remove the old `_is_url_safe()` pre-flight function entirely (or keep it only for fast user-facing error messages before the request, but the transport is the security boundary).

**Keep** `_is_url_safe()` as a fast pre-flight check for user-friendly error messages (e.g. "missing scheme"), but the **transport** is the actual security boundary. The pre-flight should NOT do DNS resolution — only validate scheme, hostname presence, etc.

### Tests

**File:** `tests/unit/test_http_get.py` (update existing + add new)

Add/update tests:
1. `test_ssrf_redirect_blocked` — mock an initial URL that returns 302 to `http://169.254.169.254/latest/meta-data/`. Assert blocked.
2. `test_ssrf_dns_rebinding_blocked` — mock DNS resolution to return a private IP at transport time. Assert blocked.
3. `test_ssrf_transport_blocks_private_ip` — directly test `SSRFSafeTransport` with various blocked IPs.
4. Existing `_is_url_safe` tests should still pass (it now only checks scheme/hostname, not DNS).

**Commit:** `fix(security): SSRF — validate IPs at transport layer, block redirect chains`

---

## §2 — Fix terminal tool: kill process group on timeout

**File:** `src/hestia/tools/builtin/terminal.py`

### Problem
`proc.kill()` only kills the shell process. Child processes spawned by the shell continue running as orphans.

### Fix

1. Set `start_new_session=True` on `asyncio.create_subprocess_shell()` so the shell and all its children are in their own process group.
2. On timeout, use `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` to kill the entire process group.
3. Keep the `PermissionError` fallback.

```python
import os
import signal

proc = await asyncio.create_subprocess_shell(
    command,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,
)
try:
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
except TimeoutError:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (PermissionError, ProcessLookupError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    await proc.wait()
    return f"TIMEOUT after {timeout}s"
```

### Also: Remove stale comment

Line 27 has `requires_confirmation=True,  # Phase 1c will enforce this`. Remove the comment (confirmation **is** enforced — we're past Phase 6). Leave `requires_confirmation=True` as-is.

### Tests

**File:** `tests/unit/test_terminal.py` (update/add)

1. `test_timeout_kills_process_group` — run a command that spawns a child process, let it timeout, verify both parent and child are dead.
2. Existing timeout tests should still pass.

**Commit:** `fix(security): terminal — kill process group on timeout, remove stale comment`

---

## §3 — Remove NameError guards in engine.py

**File:** `src/hestia/orchestrator/engine.py`

### Problem
Lines ~369-385 and ~387-408 catch `NameError` for `policy_snapshot` / `slot_snapshot` / `allowed_tools`. This means the engine knows it might reference a name before it's assigned — a code smell.

### Fix

At the **top** of `process_turn()`, before the main `try` block, initialize:

```python
allowed_tools: list[str] | None = None
policy_snapshot: str = json.dumps({"error": "policy not initialized"})
slot_snapshot: str = json.dumps({"error": "slot not initialized"})
```

Then remove **both** `except NameError:` handlers. The variables are always defined, so `NameError` can never fire. The `except (TypeError, AttributeError)` handler on the slot snapshot path should remain.

### Tests

Existing orchestrator tests cover these paths. No new tests needed, but run the full suite to verify nothing breaks.

**Commit:** `fix: initialize policy/slot snapshot vars, remove NameError guards`

---

## §4 — ArtifactStore atomic write for inline index

**File:** `src/hestia/artifacts/store.py`

### Problem
`_save_inline_index()` does `json.dump()` directly to the file. A crash mid-write corrupts `inline.json` and all inline artifacts become unreadable.

### Fix

Write to a temporary file in the same directory, then atomically replace:

```python
import tempfile

def _save_inline_index(self) -> None:
    """Save inline artifact index to disk."""
    import base64

    index_path = self._root / "inline.json"
    data = {
        "content": {
            handle: base64.b64encode(content).decode("ascii")
            for handle, content in self._inline.items()
        }
    }
    # Write to temp file + atomic rename to prevent corruption on crash
    fd, tmp_path = tempfile.mkstemp(dir=self._root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, index_path)
    except BaseException:
        os.unlink(tmp_path)
        raise
```

Add `import os` and `import tempfile` at the top of the file (not inside the function — see §5 of L16 for lazy import cleanup, but for new code use top-level from the start).

### Tests

**File:** `tests/unit/test_artifacts.py` (add)

1. `test_inline_index_atomic_write` — verify that after `_save_inline_index()`, the file exists and is valid JSON.
2. `test_inline_index_survives_crash` — mock `json.dump` to raise mid-write, verify the original `inline.json` is unchanged (not corrupted).

**Commit:** `fix: atomic write for ArtifactStore inline index`

---

## §5 — Make empty allowed_users deny-all

**File:** `src/hestia/platforms/telegram_adapter.py`

### Problem
`_is_allowed()` returns `True` when `allowed_users` is empty (`[]`). The safe default should deny all. The `SecurityAuditor` catches this, but audit isn't run by default.

### Fix

Change `_is_allowed()`:

```python
def _is_allowed(self, user_id: int, username: str | None) -> bool:
    """Check if a user is in the allowed list.

    Empty list = deny all (require explicit opt-in).
    """
    if not self._config.allowed_users:
        return False

    allowed = self._config.allowed_users
    return str(user_id) in allowed or (username is not None and username in allowed)
```

Also update **`src/hestia/config.py`** docstring for `TelegramConfig.allowed_users` to clarify: "Empty list denies all users. Populate with user IDs or usernames to allow access."

Check if `MatrixConfig` has a similar `allowed_rooms` or `allowed_users` pattern and apply the same fix if so.

### Tests

**File:** `tests/unit/test_telegram.py` or equivalent

1. `test_empty_allowed_users_denies_all` — verify `_is_allowed()` returns `False` when `allowed_users=[]`.
2. Existing tests that set `allowed_users` explicitly should still pass.
3. Update any test that relied on `[]` meaning "allow all" — those tests should now set explicit user IDs.

**Commit:** `fix(security): empty allowed_users denies all — require explicit opt-in`

---

## Handoff

`docs/handoffs/HESTIA_L15_REPORT_<YYYYMMDD>.md` + `.kimi-done` with:

```
HESTIA_KIMI_DONE=1
LOOP=L15
BRANCH=feature/l15-security-hardening
COMMIT=<sha>
TESTS=<pass count>
```

---

## Critical rules recap

1. **No secrets in code.** Never hardcode tokens, passwords, or API keys.
2. **Every section gets its own commit** with the message shown above.
3. **Run `uv run pytest tests/unit/ tests/integration/ -q`** after each commit. All must pass.
4. **Run `uv run ruff check src/ tests/`** — fix any new violations.
5. Write the `.kimi-done` file and handoff report **last**.
6. Do NOT modify files outside the scope of this spec.
7. Do NOT skip §0/carry-forward items.
