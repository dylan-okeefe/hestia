"""HTTP GET via Playwright with persistent session support."""

from urllib.parse import urlparse

from hestia.tools.browser.fetch import fetch_url
from hestia.tools.browser.session_store import normalize_domain
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool


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
            "url": {"type": "string", "description": "Full URL to fetch."},
            "wait_for_selector": {"type": "string", "description": "CSS selector to wait for."},
            "wait_seconds": {"type": "integer", "description": "Extra seconds for JS hydration."},
            "timeout_seconds": {"type": "integer", "description": "Load timeout in seconds."},
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
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return f"Invalid URL: {url}"

    domain = normalize_domain(parsed.hostname)
    result = await fetch_url(
        url,
        domain=domain,
        wait_for_selector=wait_for_selector,
        wait_seconds=wait_seconds,
        timeout_seconds=timeout_seconds,
    )
    return result.text
