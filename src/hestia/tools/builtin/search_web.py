"""Web search via DuckDuckGo HTML (no API key required).

Falls back gracefully when Tavily is unavailable. Uses the DuckDuckGo HTML
interface which returns raw, parseable HTML without JavaScript rendering.
"""

from __future__ import annotations

import html as html_module
import re
import urllib.parse
from typing import Any

from hestia.tools.builtin.http_get import SSRFSafeTransport, http_get
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

# Regex-based parsing of DuckDuckGo HTML results.
# Each result block contains: title link, URL, and snippet.
_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    r'.*?<a[^>]+class="result__url"[^>]*href="([^"]+)"[^>]*>[^<]*</a>'
    r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)

# Strip HTML tags
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(raw: str) -> str:
    return _TAG_RE.sub("", raw).strip()


def _unescape(raw: str) -> str:
    return html_module.unescape(raw)


@tool(
    name="search_web",
    public_description=(
        "Search the web via DuckDuckGo. Returns top results with title, URL, "
        "and snippet. Use this to find current information when you don't "
        "already have a specific URL."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (natural language, keywords, or a question).",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    tags=["network", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def search_web(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo HTML interface.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10)

    Returns:
        Formatted search results or error message
    """
    max_results = max(1, min(max_results, 10))
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    try:
        html = await http_get(url, timeout_seconds=30)
    except Exception as e:  # noqa: BLE001 — tool boundary
        return f"Search failed: {e}"

    matches = _RESULT_RE.findall(html)
    if not matches:
        return "No results found."

    lines: list[str] = []
    seen_urls: set[str] = set()
    for raw_redirect, raw_title, raw_url, raw_snippet in matches:
        if len(lines) >= max_results:
            break

        # DuckDuckGo redirects through their own URL; extract the real destination
        redirect_match = re.search(r"uddg=([^&]+)", raw_redirect)
        if redirect_match:
            real_url = urllib.parse.unquote(redirect_match.group(1))
        else:
            real_url = raw_redirect

        # Skip ads (DuckDuckGo ad redirects point to y.js with ad_domain)
        if "/y.js?" in real_url and "ad_domain" in real_url:
            continue

        if real_url in seen_urls:
            continue
        seen_urls.add(real_url)

        title = _unescape(_strip_tags(raw_title))
        snippet = _unescape(_strip_tags(raw_snippet))

        lines.append(f"{title}\n  {real_url}\n  {snippet}")

    if not lines:
        return "No results found."

    return "\n\n".join(lines)
