# L157 — Browser Session Persistence Handoff

**Status:** Complete
**Branch:** `feature/l157-browser-session-persistence`

## Summary

Added Playwright-based browser automation with persistent session storage.
Hestia can now scrape JavaScript-heavy authenticated sites by reusing
logged-in browser sessions.

## Changes

- `src/hestia/tools/browser/session_store.py` — `BrowserSessionStore` for
  persistent cookie/storage state per-domain under `~/.hestia/browser-sessions/`
- `src/hestia/tools/builtin/browser_login.py` — `browser_login` tool; opens a
  visible Chromium window for manual auth, then saves the session
- `src/hestia/tools/builtin/browser_get.py` — `browser_get` tool; headless
  Playwright fetch with automatic session reuse
- `src/hestia/config.py` — added `BrowserConfig` with `enabled`, `session_dir`,
  `headless`, `default_timeout_seconds`
- `src/hestia/tools/builtin/__init__.py` — exports `browser_login` and
  `browser_get`
- `src/hestia/app.py` — conditional tool registration when
  `config.browser.enabled` or Playwright is installed
- `pyproject.toml` — added `playwright>=1.40.0` to the `browser` extra;
  added `playwright` to mypy `ignore_missing_imports`
- `tests/unit/tools/test_browser_session_store.py` — tests for save/load
  cookies, storage state, list_domains, clear
- `tests/unit/tools/test_browser_tools.py` — tests for URL validation,
  ImportError handling, and mocked Playwright success paths

## Quality gates

- `pytest tests/unit/ tests/integration/ -q` — 1194 passed, 6 skipped
- `mypy src/hestia` — clean
- `ruff check src/ tests/` — clean on changed files

## Notes

Playwright is an optional dependency. Tools gracefully return an installation
message when Playwright is not available. No Playwright binaries were
installed — only the Python package dependency was added to `pyproject.toml`.
