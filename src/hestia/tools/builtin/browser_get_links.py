"""Extract hyperlinks from a page using a real browser."""

from urllib.parse import urlparse

from hestia.tools.browser.fetch import fetch_url
from hestia.tools.browser.session_store import normalize_domain
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool


@tool(
    name="browser_get_links",
    public_description=(
        "Extract direct URLs from links on a web page using a real browser. "
        "Use this when a search page shows listings but browser_get only returns "
        "visible text and not the underlying hrefs. "
        "Params: url (str), selector (str, optional) — CSS selector limiting "
        "which links to extract (e.g. 'a.job-card'). "
        "pattern (str, optional) — regex to filter link text. "
        "wait_seconds (int, default 3), timeout_seconds (int, default 60), "
        "headless (bool, default true) — set false to open a visible browser."
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
            "headless": {
                "type": "boolean",
                "description": "Run headless (default true). Set false for sites that block headless browsers.",
            },
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
    timeout_seconds: int = 60,
    headless: bool = True,
) -> str:
    """Fetch a URL with Playwright and return a list of direct link URLs.

    Returns a markdown list with link text and absolute URL, one per line.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return f"Invalid URL: {url}"

    domain = normalize_domain(parsed.hostname)
    result = await fetch_url(
        url,
        domain=domain,
        selector=selector,
        extract_links=True,
        pattern=pattern,
        wait_seconds=wait_seconds,
        timeout_seconds=timeout_seconds,
        headless=headless,
    )

    if not result.ok:
        return result.text

    if not result.links:
        return f"No links found on {url} with selector={selector!r} pattern={pattern!r}"

    lines = [f"Links from {url}:", ""]
    for link in result.links:
        text = link["text"].replace("\n", " ")
        lines.append(f"- [{text}]({link['href']})")

    return "\n".join(lines)
