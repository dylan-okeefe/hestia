"""HTTP GET via Playwright with persistent session support."""

import logging
from typing import Any
from urllib.parse import urlparse

from hestia.tools.browser.session_store import BrowserSessionStore
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
    name="browser_get",
    public_description=(
        "Fetch a web page using a real browser (Playwright). "
        "Use this for JavaScript-heavy sites like LinkedIn, Gmail, "
        "or any page that requires a logged-in session. "
        "If you've used browser_login for this domain, the saved "
        "session is reused automatically. "
        "Params: url (str), wait_for_selector (str, optional) — "
        "CSS selector to wait for before returning. "
        "wait_seconds (int, default 3) — extra time to let JS hydrate. "
        "timeout_seconds (int, default 30)."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL to fetch (e.g. https://example.com)."},
            "wait_for_selector": {"type": "string", "description": "Optional CSS selector to wait for before returning."},
            "wait_seconds": {"type": "integer", "description": "Extra seconds to wait for JS hydration (default 3)."},
            "timeout_seconds": {"type": "integer", "description": "Page load timeout in seconds (default 30)."},
        },
        "required": ["url"],
    },
    max_inline_chars=6000,
    tags=["network", "browser", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def browser_get(
    url: str,
    wait_for_selector: str = "",
    wait_seconds: int = 3,
    timeout_seconds: int = 30,
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

    domain = _normalize_domain(parsed.hostname)
    store = BrowserSessionStore()
    storage_state = _load_session(store, domain)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context_kwargs: dict[str, Any] = {
            "viewport": _VIEWPORT,
            "user_agent": _USER_AGENT,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        if storage_state is not None:
            context_kwargs["storage_state"] = storage_state
            logger.debug("Loaded stored session for %s", domain)

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        # Mask headless-detection flags
        await page.add_init_script(
            """
            () => {
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            }
            """
        )

        text = ""
        try:
            await page.goto(
                url,
                timeout=timeout_seconds * 1000,
                wait_until="domcontentloaded",
            )

            if wait_for_selector:
                await page.wait_for_selector(
                    wait_for_selector, timeout=timeout_seconds * 1000
                )
            else:
                # Give JS-heavy apps (LinkedIn, etc.) time to hydrate
                await page.wait_for_timeout(wait_seconds * 1000)

            text = await _extract_text(page)

            # Detect bot-protection pages and return a clear error
            lower_text = text.lower()
            if "cloudflare" in lower_text and ("verification" in lower_text or "security" in lower_text):
                return f"[BLOCKED] Cloudflare verification page for {url}. The site is blocking automated access."
            if "additional verification required" in lower_text:
                return f"[BLOCKED] Bot protection page for {url}. The site is blocking automated access."

            # Persist refreshed session state so subsequent calls stay authenticated.
            # Save both storage_state (cookies + localStorage) and cookies for
            # backward compatibility.
            try:
                refreshed_storage = await context.storage_state()
                store.save_storage(domain, refreshed_storage)
                refreshed_cookies = await context.cookies()
                store.save_cookies(domain, refreshed_cookies)
            except Exception as exc:
                logger.warning("Failed to persist session for %s: %s", domain, exc)

        except Exception as exc:
            logger.warning("browser_get partial failure for %s: %s", url, exc)
            # Try to salvage whatever content loaded before the error
            try:
                text = await _extract_text(page)
            except Exception:
                pass
            if not text:
                return f"Error fetching {url}: {exc}"

        finally:
            await context.close()
            await browser.close()

        return text or ""


async def _extract_text(page: Any) -> str:
    """Extract readable text from the page, stripping scripts/styles/modals."""
    return await page.evaluate(
        """() => {
            document.querySelectorAll(
                "script, style, nav, footer, iframe, noscript, aside, " +
                "[aria-modal='true'], [role='dialog'], .artdeco-modal, .artdeco-modal-overlay"
            ).forEach(el => el.remove());
            return document.body.innerText || "";
        }"""
    )
