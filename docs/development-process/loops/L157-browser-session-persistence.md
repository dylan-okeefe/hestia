# L157 — Browser Session Persistence with Playwright

**Status:** Spec only. Feature branch work; do not merge to develop until release-prep merge sequence.

**Branch:** `feature/l157-browser-session-persistence` (from `develop`)

## Goal

Add Playwright-based browser automation so Hestia can scrape JavaScript-heavy authenticated sites (LinkedIn, etc.) by reusing Dylan's logged-in browser sessions.

## Review carry-forward

- *(none)*

## Scope

### §1 — Browser session storage module

Create `src/hestia/tools/browser/session_store.py`:

```python
"""Persistent browser session storage using Playwright."""

import json
from pathlib import Path
from typing import Any


class BrowserSessionStore:
    """Manages persistent browser contexts for authenticated sites.

    Stores cookies and localStorage per-domain under
    ``~/.hestia/browser-sessions/<domain>/`` so logins survive restarts.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.home() / ".hestia" / "browser-sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, domain: str) -> Path:
        safe = domain.replace(".", "_")
        path = self.base_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_cookies(self, domain: str, cookies: list[dict[str, Any]]) -> None:
        path = self._session_dir(domain) / "cookies.json"
        path.write_text(json.dumps(cookies, indent=2))

    def load_cookies(self, domain: str) -> list[dict[str, Any]]:
        path = self._session_dir(domain) / "cookies.json"
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def save_storage(self, domain: str, storage_state: dict[str, Any]) -> None:
        path = self._session_dir(domain) / "storage_state.json"
        path.write_text(json.dumps(storage_state, indent=2))

    def load_storage(self, domain: str) -> dict[str, Any] | None:
        path = self._session_dir(domain) / "storage_state.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_domains(self) -> list[str]:
        return [d.name.replace("_", ".") for d in self.base_dir.iterdir() if d.is_dir()]

    def clear(self, domain: str) -> None:
        import shutil
        shutil.rmtree(self._session_dir(domain), ignore_errors=True)
```

Add to `pyproject.toml` under a new `browser` extra:
```toml
browser = [
    "playwright>=1.40.0",
]
```

Commit: `feat(tools): browser session store for persistent auth`

### §2 — `browser_login` tool

Create `src/hestia/tools/builtin/browser_login.py`:

```python
"""Tool to capture authenticated browser sessions via visible browser."""

import asyncio
import logging
from urllib.parse import urlparse

from hestia.tools.browser.session_store import BrowserSessionStore
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)


@tool(
    name="browser_login",
    public_description=(
        "Open a visible browser window for you to log into a site. "
        "After you close the browser, the session (cookies + localStorage) "
        "is saved for future browser_get calls. "
        "Params: url (str) — the login page URL. "
        "Returns the saved domain name or an error message."
    ),
    tags=["network", "browser", "builtin"],
)
async def browser_login(url: str) -> str:
    """Open a visible browser for manual login, then save the session."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            "Playwright is not installed. Install with: "
            "uv pip install playwright && playwright install chromium"
        )

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return f"Invalid URL: {url}"

    domain = parsed.hostname
    store = BrowserSessionStore()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        # Wait for user to log in and close browser
        msg = (
            f"Browser opened for {domain}. Please log in, "
            f"then close the browser window to save the session."
        )
        logger.info(msg)

        # Poll until all pages are closed (user closed the browser)
        while len(browser.contexts) > 0 and len(browser.contexts[0].pages) > 0:
            await asyncio.sleep(1)

        # Save session state
        storage = await context.storage_state()
        store.save_storage(domain, storage)

        # Also extract and save cookies separately for compatibility
        cookies = await context.cookies()
        store.save_cookies(domain, cookies)

        await context.close()
        await browser.close()

    return f"Session saved for {domain}. {len(cookies)} cookies stored."
```

Commit: `feat(tools): browser_login tool for manual auth capture`

### §3 — `browser_get` tool

Create `src/hestia/tools/builtin/browser_get.py`:

```python
"""HTTP GET via Playwright with persistent session support."""

import logging
from urllib.parse import urlparse

from hestia.tools.browser.session_store import BrowserSessionStore
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)


@tool(
    name="browser_get",
    public_description=(
        "Fetch a web page using a real browser (Playwright). "
        "Use this for JavaScript-heavy sites like LinkedIn, Gmail, "
        "or any page that requires a logged-in session. "
        "If you've used browser_login for this domain, the saved "
        "session is reused automatically. "
        "Params: url (str), wait_for_selector (str, optional) — "
        "CSS selector to wait for before returning. "
        "timeout_seconds (int, default 30)."
    ),
    max_inline_chars=6000,
    tags=["network", "browser", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def browser_get(
    url: str, wait_for_selector: str = "", timeout_seconds: int = 30
) -> str:
    """Fetch a URL using Playwright with session persistence."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            "Playwright is not installed. Install with: "
            "uv pip install playwright && playwright install chromium"
        )

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return f"Invalid URL: {url}"

    domain = parsed.hostname
    store = BrowserSessionStore()
    storage_state = store.load_storage(domain)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context_kwargs: dict = {}
        if storage_state is not None:
            context_kwargs["storage_state"] = storage_state
            logger.debug("Loaded stored session for %s", domain)

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        try:
            await page.goto(url, timeout=timeout_seconds * 1000, wait_until="networkidle")

            if wait_for_selector:
                await page.wait_for_selector(
                    wait_for_selector, timeout=timeout_seconds * 1000
                )

            # Extract text content (skip scripts/styles)
            text = await page.evaluate(
                """() => {
                    const scripts = document.querySelectorAll('script, style, nav, footer');
                    scripts.forEach(el => el.remove());
                    return document.body.innerText;
                }"""
            )

            # Update stored cookies in case they refreshed
            cookies = await context.cookies()
            store.save_cookies(domain, cookies)

            return text or ""

        except Exception as exc:
            logger.exception("browser_get failed for %s", url)
            return f"Error fetching {url}: {exc}"
        finally:
            await context.close()
            await browser.close()
```

Commit: `feat(tools): browser_get tool with session reuse`

### §4 — Config wiring and tool registration

Add `BrowserConfig` to `src/hestia/config.py`:

```python
@dataclass
class BrowserConfig(_ConfigFromEnv):
    """Configuration for browser automation tools."""

    _ENV_PREFIX = "BROWSER"

    enabled: bool = False
    session_dir: Path = field(
        default_factory=lambda: Path.home() / ".hestia" / "browser-sessions"
    )
    headless: bool = True
    default_timeout_seconds: int = 30
```

Wire into `HestiaConfig`:
```python
browser: BrowserConfig = field(default_factory=BrowserConfig)
```

Register tools in `src/hestia/tools/builtin/__init__.py` and `src/hestia/tools/builtin/registry.py` (or wherever tools are registered). The `browser_login` and `browser_get` tools should only be registered when `config.browser.enabled` is True OR when Playwright is installed.

Commit: `feat(config): BrowserConfig and tool registration`

### §5 — Tests

Create `tests/unit/tools/test_browser_session_store.py`:
- Test save/load cookies
- Test save/load storage state
- Test list_domains
- Test clear

Create `tests/unit/tools/test_browser_tools.py`:
- Mock Playwright where possible
- Test browser_login validation (invalid URL)
- Test browser_get validation (invalid URL)
- Test ImportError when Playwright not installed

Run quality gates:
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

Commit: `test(tools): browser session store and tool tests`

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `ruff check src/` remains at baseline or better
- `.kimi-done` includes `LOOP=L157`

## Handoff

- Write `docs/handoffs/L157-browser-session-persistence-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to idle
