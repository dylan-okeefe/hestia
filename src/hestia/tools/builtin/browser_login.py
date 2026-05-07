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
