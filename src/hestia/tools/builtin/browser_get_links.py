"""Extract hyperlinks from a page using a real browser."""

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from hestia.tools.browser.session_store import BrowserSessionStore
from hestia.tools.browser.stealth import (
    STEALTH_LAUNCH_ARGS,
    apply_stealth_async,
    stealth_context_kwargs,
)
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)

# Realistic viewport and UA to reduce headless-detection flags
_VIEWPORT = {"width": 1920, "height": 1080}
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def _normalize_domain(hostname: str) -> str:
    """Return canonical domain, stripping www. prefix if present."""
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def _load_session(store: BrowserSessionStore, domain: str) -> dict[str, Any] | None:
    """Load storage_state for domain, falling back to cookies.json."""
    storage = store.load_storage(domain)
    if storage is not None:
        return storage

    cookies = store.load_cookies(domain)
    if cookies:
        logger.debug("No storage_state for %s; falling back to cookies.json", domain)
        return {"cookies": cookies, "origins": []}

    return None


@tool(
    name="browser_get_links",
    public_description=(
        "Extract direct URLs from links on a web page using a real browser. "
        "Use this when a search page shows listings but browser_get only returns "
        "visible text and not the underlying hrefs. "
        "Params: url (str), selector (str, optional) — CSS selector limiting "
        "which links to extract (e.g. 'a.job-card'). "
        "pattern (str, optional) — regex to filter link text. "
        "wait_seconds (int, default 3), timeout_seconds (int, default 30)."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL of the page to extract links from."},
            "selector": {
                "type": "string",
                "description": "Optional CSS selector to scope link extraction (e.g. 'a.job-title').",
            },
            "pattern": {
                "type": "string",
                "description": "Optional regex to filter links by their visible text.",
            },
            "wait_seconds": {"type": "integer", "description": "Extra seconds for JS hydration."},
            "timeout_seconds": {"type": "integer", "description": "Load timeout in seconds."},
        },
        "required": ["url"],
    },
    max_inline_chars=6000,
    tags=["network", "browser", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def browser_get_links(
    url: str,
    selector: str = "a",
    pattern: str = "",
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
) -> str:
    """Fetch a URL with Playwright and return a list of direct link URLs.

    Returns a markdown list with link text and absolute URL, one per line.
    """
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
    storage_state = _load_session(store, domain)
    store.update_metadata(domain, last_used=datetime.now(UTC))

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=STEALTH_LAUNCH_ARGS,
        )

        context = await browser.new_context(
            **stealth_context_kwargs(storage_state)
        )
        page = await context.new_page()
        await apply_stealth_async(page)

        try:
            await page.goto(
                url,
                timeout=timeout_seconds * 1000,
                wait_until="networkidle",
            )
            await page.wait_for_timeout(wait_seconds * 1000)

            links = await page.evaluate(
                """(selector, pattern) => {
                    const re = pattern ? new RegExp(pattern, 'i') : null;
                    const seen = new Set();
                    const results = [];
                    document.querySelectorAll(selector).forEach(el => {
                        const href = el.href || el.closest('a')?.href;
                        if (!href) return;
                        const text = (el.innerText || el.textContent || '').trim();
                        if (re && !re.test(text)) return;
                        if (seen.has(href)) return;
                        seen.add(href);
                        results.push({text: text.slice(0, 200), href: href});
                    });
                    return results;
                }""",
                selector,
                pattern,
            )

            try:
                refreshed_storage = await context.storage_state()
                store.save_storage(domain, refreshed_storage)
                refreshed_cookies = await context.cookies()
                store.save_cookies(domain, refreshed_cookies)
            except Exception as exc:
                logger.warning("Failed to persist session for %s: %s", domain, exc)

        except Exception as exc:
            logger.warning("browser_get_links partial failure for %s: %s", url, exc)
            return f"Error fetching {url}: {exc}"

        finally:
            await context.close()
            await browser.close()

    if not links:
        return f"No links found on {url} with selector={selector!r} pattern={pattern!r}"

    lines = [f"Links from {url}:", ""]
    for link in links:
        text = link["text"].replace("\n", " ")
        lines.append(f"- [{text}]({link['href']})")

    return "\n".join(lines)
