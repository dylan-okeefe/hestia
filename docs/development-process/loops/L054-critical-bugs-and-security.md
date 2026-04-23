# L054: Critical Bugs & Security Quick Wins

**Status:** Complete — merged to `feature/v0.10.1-pre-publication-prep`  
**Branch:** `feature/v0.10.1-pre-publication-prep`  
**Scope:** Small, isolated fixes from Copilot evaluation. No architectural changes.

---

## Items

| ID | Issue | File | Fix |
|----|-------|------|-----|
| B1.1 | Duplicate logger definition | `policy/default.py` | Remove second `getLogger` call |
| B1.2 | AuditGroup.invoke loses flags | `cli.py` | Use `invoke_without_command=True`, simplify invoke |
| B1.3 | Empty `setup` CLI group | `cli.py` | Remove unused group |
| B1.4 | Unimplemented `skill test` command | `cli.py`, `commands/__init__.py` | Remove stub command |
| B2.1 | SSRF docstring overstates DNS rebinding | `tools/builtin/http_get.py` | Make docstring accurate |
| B2.3 | Internal errors surfaced verbatim | `orchestrator/engine.py` | Sanitize before `respond_callback` |
| B2.4 | Config-as-Python undersold | `README.md` | Add one-sentence warning |

---

## B1.2 Detail: AuditGroup.invoke

Current implementation uses `ctx.protected_args` (a Click internal) to detect whether a subcommand was given. When flags like `--json` are passed, they're not in `protected_args`, so the default-to-`run` logic fails silently.

Fix: Use Click's public `invoke_without_command=True` group option and check `ctx.invoked_subcommand`.

## B2.3 Detail: Error Sanitization

`_handle_unexpected_error` in `engine.py` does `await respond_callback(f"Error: {error}")` which leaks SQL errors, file paths, and internal stack traces to end users.

Fix: Add `_sanitize_user_error(error)` helper that:
- Passes through `HestiaError` subclasses intact (they're intentionally user-friendly)
- Shows generic "Something went wrong" for unknown `Exception`s
- Always logs the full exception for debugging

## B2.1 Detail: SSRF Docstring

`SSRFSafeTransport` docstring claims it "prevents both redirect-based SSRF and DNS rebinding attacks." The DNS rebinding claim is overstated — `getaddrinfo` and `httpx` may do separate DNS lookups, so a TTL-based rebinding race is possible. The docstring should be accurate.

---

## Test Plan

- `uv run pytest tests/ -q` — ensure no regressions
- `uv run ruff check src/ tests/` — lint
- `uv run mypy src/hestia/orchestrator/engine.py src/hestia/cli.py src/hestia/policy/default.py src/hestia/tools/builtin/http_get.py` — type check changed files
