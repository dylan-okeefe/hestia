"""HTTP GET via Playwright with persistent session support."""

import logging
from typing import Any
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

        context_kwargs: dict[str, Any] = {}
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
