"""Tool to capture authenticated browser sessions via visible browser."""

import asyncio
import logging
from urllib.parse import urlparse

from hestia.tools.browser.session_store import BrowserSessionStore
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)

_VIEWPORT = {"width": 1920, "height": 1080}
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# How long to wait for the user to finish login before giving up
_LOGIN_TIMEOUT_SECONDS = 600  # 10 minutes
# How often to snapshot session state to disk while the browser is open
_SNAPSHOT_INTERVAL_SECONDS = 5


def _normalize_domain(hostname: str) -> str:
    """Return canonical domain, stripping www. prefix if present."""
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


@tool(
    name="browser_login",
    public_description=(
        "Open a visible browser window for you to log into a site. "
        "After you close the browser, the session (cookies + localStorage) "
        "is saved for future browser_get calls. "
        "Params: url (str) — the login page URL. "
        "Returns the saved domain name or an error message."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The login page URL (e.g. https://linkedin.com/login)."},
        },
        "required": ["url"],
    },
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

    domain = _normalize_domain(parsed.hostname)
    store = BrowserSessionStore()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport=_VIEWPORT,
            user_agent=_USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()

        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")

        msg = (
            f"Browser opened for {domain}. Please log in, "
            f"then close the browser window to save the session."
        )
        logger.info(msg)

        # Poll until all pages are closed (user closed the browser) or timeout.
        # Snapshot storage_state periodically so we already have the latest
        # state on disk if the user kills the browser process.
        elapsed = 0
        last_snapshot = 0
        while elapsed < _LOGIN_TIMEOUT_SECONDS:
            contexts = browser.contexts
            if not contexts or not contexts[0].pages:
                break

            if elapsed - last_snapshot >= _SNAPSHOT_INTERVAL_SECONDS:
                try:
                    storage = await context.storage_state()
                    store.save_storage(domain, storage)
                    cookies = await context.cookies()
                    store.save_cookies(domain, cookies)
                    last_snapshot = elapsed
                except Exception as exc:
                    logger.debug("Periodic snapshot failed (browser may be closing): %s", exc)

            await asyncio.sleep(1)
            elapsed += 1

        # Final save: try to capture state from the still-open context.
        # If the browser was already closed by the user, fall back to the
        # last periodic snapshot on disk.
        try:
            storage = await context.storage_state()
            store.save_storage(domain, storage)
            cookies = await context.cookies()
            store.save_cookies(domain, cookies)
        except Exception as exc:
            logger.warning(
                "Final session capture failed for %s (%s). "
                "Using last periodic snapshot if available.",
                domain,
                exc,
            )
            cookies = store.load_cookies(domain)

        try:
            await context.close()
            await browser.close()
        except Exception:
            pass

    cookie_count = len(cookies) if isinstance(cookies, list) else 0
    return (
        f"Session saved for {domain}. {cookie_count} cookies stored.\n\n"
        "You can also manage this session (and re-authenticate later) "
        "from the Browser Sessions page on the Hestia dashboard."
    )
