# Hestia — Phase 7: Critical Cleanup Pass

> **Branch:** `feature/phase-7-cleanup` from `develop`
> **Scope:** 7 targeted fixes — bugs, security, and code hygiene. No new features.
> **Estimated effort:** 1–2 hours. All changes are surgical.

---

## Prerequisites

```bash
git checkout develop
git pull origin develop
git checkout -b feature/phase-7-cleanup
uv sync
uv run pytest tests/unit/ tests/integration/ -q   # confirm green baseline
```

Record baseline test count: ________

---

## §1 — Fix `tool_chain` UnboundLocalError in orchestrator

**File:** `src/hestia/orchestrator/engine.py`

**Bug:** `tool_chain: list[str] = []` is defined at line 187, inside the inner `try` block that starts at line 150. The `except Exception` handler at line 302 references `tool_chain` at line 320 (inside `json.dumps(tool_chain)`). If any exception occurs between lines 150–186 — during context building, history loading, or slot acquisition — `tool_chain` has not been assigned yet and the error handler itself crashes with `UnboundLocalError`, masking the real exception.

**Fix:**

Move the `tool_chain` initialization to immediately after `turn = self._create_turn(...)`, before the inner try block. The line should read:

```python
turn = self._create_turn(session.id, user_message)
await self._persist_turn(turn)
tool_chain: list[str] = []   # <-- move here from line 187
```

Remove the duplicate at line 187. The `while` loop that appends to `tool_chain` will still work — it just sees the variable from the enclosing scope.

**Verify:** Write a unit test `tests/unit/test_orchestrator_errors.py::test_tool_chain_unbound_error` that mocks `ContextBuilder.build()` to raise `RuntimeError("build failed")`, then asserts that `process_turn` raises/handles the error cleanly (the failure bundle should contain `tool_chain: "[]"`, not crash).

---

## §2 — Fix `import sqlalchemy as sa` at bottom of db.py

**File:** `src/hestia/persistence/db.py`

**Bug:** Line 69 has `import sqlalchemy as sa  # noqa: E402` but `sa` is used on line 34 inside `connect()` as `sa.text("SELECT 1")`. This works by accident because `connect()` is called after module load, but it violates PEP 8, confuses readers, and will break if anyone adds module-level code referencing `sa`.

**Fix:**

1. Delete line 69 (`import sqlalchemy as sa  # noqa: E402`).
2. Add `import sqlalchemy as sa` to the import block at the top of the file, after the existing imports (around line 5).

The file's import block should look like:

```python
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from hestia.errors import PersistenceError
from hestia.persistence.schema import metadata
```

**Verify:** `uv run python -c "from hestia.persistence.db import Database"` — should import cleanly.

---

## §3 — Add path sandboxing to `list_dir`

**File:** `src/hestia/tools/builtin/list_dir.py`

**Bug:** `read_file` and `write_file` both use `check_path_allowed()` from `path_utils.py` for path sandboxing. `list_dir` does not — it accepts any path string and lists it without validation. The model could enumerate `/etc`, `~/.ssh`, `/root`, or any other directory on the system.

**Fix:**

Convert `list_dir` to a factory function matching the pattern used by `read_file` and `write_file`.

Replace the entire file with:

```python
"""List directory tool (factory)."""

from pathlib import Path
from typing import Any

from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.capabilities import READ_LOCAL
from hestia.tools.metadata import tool


def make_list_dir_tool(allowed_roots: list[str]) -> Any:
    """Create a list_dir tool with path sandboxing.

    Args:
        allowed_roots: List of allowed root directories

    Returns:
        The list_dir tool function
    """

    @tool(
        name="list_dir",
        public_description="List the contents of a directory.",
        tags=["system", "builtin"],
        capabilities=[READ_LOCAL],
    )
    async def list_dir(path: str = ".", max_entries: int = 200) -> str:
        """List files and directories at the given path.

        Returns a formatted listing with file types and sizes.
        Caps output at max_entries to avoid flooding context.
        """
        # Check path sandboxing
        if error := check_path_allowed(path, allowed_roots):
            return error

        target = Path(path)
        if not target.is_dir():
            return f"Error: {path} is not a directory"

        all_items = sorted(target.iterdir())
        entries = []
        for i, item in enumerate(all_items):
            if i >= max_entries:
                entries.append(f"... ({len(all_items) - max_entries} more entries)")
                break
            kind = "dir" if item.is_dir() else "file"
            size = ""
            if item.is_file():
                size = f" ({item.stat().st_size} bytes)"
            entries.append(f"  [{kind}] {item.name}{size}")

        if not entries:
            return f"{path}: (empty)"

        return f"{path}:\n" + "\n".join(entries)

    return list_dir
```

**Then update `src/hestia/tools/builtin/__init__.py`:**

Change: `from hestia.tools.builtin.list_dir import list_dir`
To: `from hestia.tools.builtin.list_dir import make_list_dir_tool`

Update `__all__` to replace `"list_dir"` with `"make_list_dir_tool"`.

**Then update `src/hestia/cli.py`:**

In the imports at the top, change `list_dir` to `make_list_dir_tool`.

In the `cli()` function where tools are registered, find the line:
```python
tool_registry.register(list_dir)
```
Replace with:
```python
tool_registry.register(make_list_dir_tool(cfg.storage.allowed_roots))
```

**Verify:** Add test `tests/unit/test_path_sandboxing.py::test_list_dir_rejects_outside_root`:

```python
@pytest.mark.asyncio
async def test_list_dir_rejects_outside_root(tmp_path):
    tool_fn = make_list_dir_tool([str(tmp_path / "allowed")])
    result = await tool_fn.__wrapped__("/etc")
    assert "Access denied" in result
```

Also add `test_list_dir_allows_inside_root` that creates a temp directory inside the allowed root and verifies it lists correctly.

---

## §4 — Fix duplicate CliConfirmHandler instances

**File:** `src/hestia/cli.py`

**Bug:** In `chat`, `ask`, `schedule_run`, and possibly other commands, a `CliConfirmHandler()` is stored in `ctx.obj["confirm_callback"]` (e.g., line 284), but then a *different* `CliConfirmHandler()` instance is passed to the Orchestrator constructor (e.g., line 307). If `CliConfirmHandler` ever gains state (confirmation history, logging), these would diverge silently.

**Fix:**

In every command that creates an Orchestrator with a confirm callback, use the stored instance instead of creating a new one. Find every occurrence of:

```python
confirm_callback=CliConfirmHandler(),
```

inside an Orchestrator constructor and replace with:

```python
confirm_callback=ctx.obj["confirm_callback"],
```

Affected commands (search for `CliConfirmHandler()` inside async inner functions):
- `chat` (the `_chat()` inner function)
- `ask` (the `_ask()` inner function)
- `schedule_run` (the `_run()` inner function)
- Any others — search the file for `CliConfirmHandler()` to be sure

Do NOT change the line that initially stores the handler in `ctx.obj` — that's correct.

**Verify:** `grep -n "CliConfirmHandler()" src/hestia/cli.py` should show only the lines where `ctx.obj["confirm_callback"] = CliConfirmHandler()` is set, not any inside Orchestrator constructors.

---

## §5 — Remove unsandboxed tool fallbacks

**Files:** `src/hestia/tools/builtin/read_file.py`, `src/hestia/tools/builtin/write_file.py`

**Problem:** Both files ship a factory function (sandboxed) AND a module-level unsandboxed version "for backward compatibility." The unsandboxed versions are exported from `__init__.py` and can be imported directly by tests or other code, silently bypassing path sandboxing.

**Fix for `read_file.py`:**

Delete everything after the factory function. Remove lines 60–97 (the `_default_read_file` function and the module-level `read_file = tool(...)(_default_read_file)` assignment). The file should end after `return read_file` in the factory.

**Fix for `write_file.py`:**

Delete everything after the factory function. Remove lines 46–63 (the `_default_write_file` function and the module-level `write_file = tool(...)(_default_write_file)` assignment). The file should end after `return write_file` in the factory.

**Fix for `__init__.py`:**

Remove the direct imports of `read_file` and `write_file` (the module-level unsandboxed versions):
- Remove `read_file` from the import of `read_file.py` (keep only `make_read_file_tool`)
- Remove `write_file` from the import of `write_file.py` (keep only `make_write_file_tool`)
- Remove `"read_file"` and `"write_file"` from `__all__`

**Verify:** `grep -rn "from hestia.tools.builtin import.*\bread_file\b" tests/ src/` — should find zero hits importing the bare `read_file` or `write_file`. If any test imports them directly, update those tests to use the factory with `allowed_roots=["/tmp"]` or similar.

Run the full test suite: `uv run pytest tests/unit/ tests/integration/ -q`

---

## §6 — Add SSRF protection to http_get

**File:** `src/hestia/tools/builtin/http_get.py`

**Problem:** The tool accepts any URL with no filtering. The model could fetch `http://169.254.169.254/latest/meta-data/` (cloud instance metadata), `http://localhost:8080/admin`, or any internal service. This is a server-side request forgery (SSRF) vulnerability.

**Fix:**

Add a URL validation function that blocks private/internal IP ranges and localhost. Replace the entire file with:

```python
"""HTTP GET tool with SSRF protection."""

import ipaddress
import socket
from urllib.parse import urlparse

from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

# IP ranges that must never be fetched
_BLOCKED_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),         # private class A
    ipaddress.ip_network("172.16.0.0/12"),      # private class B
    ipaddress.ip_network("192.168.0.0/16"),     # private class C
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


def _is_url_safe(url: str) -> str | None:
    """Check if a URL is safe to fetch.

    Returns an error message if blocked, None if safe.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return f"Invalid URL: {url}"

    if not parsed.scheme:
        return f"Missing URL scheme (use http:// or https://): {url}"

    if parsed.scheme not in ("http", "https"):
        return f"Unsupported scheme '{parsed.scheme}' — only http and https are allowed"

    hostname = parsed.hostname
    if not hostname:
        return f"No hostname in URL: {url}"

    # Resolve hostname to IP and check against blocked ranges
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return f"Cannot resolve hostname: {hostname}"

    for family, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        for blocked in _BLOCKED_RANGES:
            if ip in blocked:
                return f"Access denied: {hostname} resolves to blocked range ({blocked})"

    return None


@tool(
    name="http_get",
    public_description="Fetch the contents of a URL via HTTP GET.",
    max_inline_chars=6000,
    tags=["network", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def http_get(url: str, timeout_seconds: int = 30) -> str:
    """Fetch a URL and return its text content.

    Returns the response body as text, capped by the tool's max_inline_chars.
    Large responses are automatically promoted to artifacts by the registry.
    Blocks requests to private/internal IP ranges for SSRF protection.
    """
    # SSRF check
    if error := _is_url_safe(url):
        return error

    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
```

**Verify:** Add tests in `tests/unit/test_builtin_tools_new.py` (or a new file `tests/unit/test_http_get_ssrf.py`):

```python
import pytest
from hestia.tools.builtin.http_get import _is_url_safe

class TestSSRFProtection:
    def test_blocks_localhost(self):
        assert _is_url_safe("http://localhost/admin") is not None
        assert "blocked range" in _is_url_safe("http://127.0.0.1/secret")

    def test_blocks_private_ranges(self):
        assert _is_url_safe("http://10.0.0.1/internal") is not None
        assert _is_url_safe("http://192.168.1.1/router") is not None
        assert _is_url_safe("http://172.16.0.1/internal") is not None

    def test_blocks_cloud_metadata(self):
        assert _is_url_safe("http://169.254.169.254/latest/meta-data/") is not None

    def test_blocks_non_http_schemes(self):
        assert _is_url_safe("file:///etc/passwd") is not None
        assert _is_url_safe("ftp://example.com/file") is not None

    def test_allows_public_urls(self):
        # Only test URL parsing, not actual resolution
        # Public hostnames may fail in CI without network
        assert _is_url_safe("http://1.1.1.1/") is None
        assert _is_url_safe("https://93.184.216.34/") is None  # example.com IP
```

---

## §7 — Remove dead `COMPRESSING` state

**Files:**
- `src/hestia/orchestrator/types.py`
- `src/hestia/orchestrator/transitions.py`

**Problem:** `TurnState.COMPRESSING` is defined with transitions but no code path ever transitions to it. It's dead code that clutters the state machine and confuses readers.

**Fix:**

In `types.py`, remove:
```python
COMPRESSING = "compressing"  # reserved for Phase 3
```

In `transitions.py`, remove the entire `TurnState.COMPRESSING` entry from `ALLOWED_TRANSITIONS`:
```python
TurnState.COMPRESSING: {
    TurnState.BUILDING_CONTEXT,  # compression done, rebuild context
    TurnState.FAILED,
},
```

Also check if `COMPRESSING` appears anywhere else in the codebase:
```bash
grep -rn "COMPRESSING" src/ tests/
```

Remove any references. If `test_turn_state_machine.py` tests transitions involving `COMPRESSING`, update or remove those test cases.

**Note:** If the project intends to implement context compression later, that's fine — add the state back when the feature is built. Dead code with "reserved for Phase 3" comments 4 phases later is just clutter.

**Verify:** Full test suite passes. `grep -rn "COMPRESSING\|compressing" src/` returns zero hits.

---

## Final checklist

After all 7 changes:

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/hestia/persistence/db.py src/hestia/orchestrator/engine.py src/hestia/tools/builtin/
```

Expected: all tests pass (count should be baseline + new tests from §1, §3, §6), no ruff errors on touched files.

**Commit and push:**

```bash
git add -A
git commit -m "fix: phase 7 cleanup — bugs, security, dead code

- Fix tool_chain UnboundLocalError in orchestrator error handler
- Fix import ordering in db.py
- Add path sandboxing to list_dir (factory pattern)
- Fix duplicate CliConfirmHandler instances in CLI
- Remove unsandboxed read_file/write_file fallbacks
- Add SSRF protection to http_get (block private IP ranges)
- Remove dead COMPRESSING state from turn machine"
git push origin feature/phase-7-cleanup
```

**Handoff report:**

Update `docs/HANDOFF_STATE.md`:
- Branch: `feature/phase-7-cleanup`
- Phase: 7 complete
- Test count: (new count)
- Verdict: (pass/fail)
- Any issues encountered during the fixes

---

## Orchestration — `.kimi-done` artifact (required for Cursor)

After the handoff report edits above and a **successful** `git push` of the cleanup branch, create a repo-root file **`.kimi-done`** (UTF-8, key/value lines, no secrets):

```text
HESTIA_KIMI_DONE=1
SPEC=docs/design/kimi-hestia-phase-7-cleanup.md
BRANCH=feature/phase-7-cleanup
PYTEST=<last line of `uv run pytest tests/unit/ tests/integration/ -q`>
GIT_HEAD=<output of `git rev-parse HEAD`>
```

Rules:

1. Write `.kimi-done` only when work is complete (or definitively abandoned — then set `HESTIA_KIMI_DONE=0` and add `ABORT_REASON=...`).
2. Do not commit `.kimi-done` (it is gitignored). Cursor uses it as a completion signal before review.
3. If you must re-run Kimi, delete any stale `.kimi-done` first (orchestration scripts do this before launch).
