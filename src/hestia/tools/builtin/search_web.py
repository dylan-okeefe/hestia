"""Web search via Bing HTML (no API key required).

Uses curl_cffi with browser impersonation to bypass bot detection.
Extracts search results from Bing's HTML response and decodes
redirect URLs to show real destinations.
"""

from __future__ import annotations

import base64
import html as html_module
import re
import urllib.parse

from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

try:
    from curl_cffi.requests import AsyncSession

    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False

# Strip HTML tags
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(raw: str) -> str:
    return _TAG_RE.sub("", raw).strip()


def _unescape(raw: str) -> str:
    return html_module.unescape(raw)


def _decode_bing_redirect(url: str) -> str:
    """Decode Bing's redirect URL to get the real destination."""
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        u = params.get("u", [""])[0]
        if u.startswith("a1"):
            b64 = u[2:]
            b64 += "=" * (4 - len(b64) % 4)
            return base64.b64decode(b64).decode("utf-8")
    except Exception:
        pass
    return url


@tool(
    name="search_web",
    public_description=(
        "Search the web via Bing. Returns top results with title, URL, "
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
    """Search the web via Bing HTML interface.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10)

    Returns:
        Formatted search results or error message
    """
    try:
        max_results = int(max_results)
    except (ValueError, TypeError):
        max_results = 5
    max_results = max(1, min(max_results, 10))
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded}"

    html = ""
    try:
        if _CURL_CFFI_AVAILABLE:
            async with AsyncSession() as s:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "en-US,en;q=0.5",
                    "Referer": "https://www.bing.com/",
                }
                r = await s.get(url, headers=headers, impersonate="chrome131", timeout=30)
                html = r.text
        else:
            from hestia.tools.builtin.http_get import http_get

            html = await http_get(url, timeout_seconds=30)
    except Exception as e:  # noqa: BLE001 — tool boundary
        return f"Search failed: {e}"

    if "captcha" in html.lower():
        return "Search blocked by CAPTCHA. Try a more specific query or search directly on job boards."

    # Parse Bing results - look for h2 > a patterns
    blocks = re.findall(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?</h2>', html, re.DOTALL)
    if not blocks:
        return "No results found."

    lines: list[str] = []
    seen_urls: set[str] = set()
    for raw_href, raw_title in blocks:
        if len(lines) >= max_results:
            break

        title = _unescape(_strip_tags(raw_title)).strip()
        # Skip video results and navigation
        if not title or "video" in title.lower() or title.lower() in ("more videos",):
            continue

        real_url = _decode_bing_redirect(raw_href.replace("&amp;", "&"))

        if real_url in seen_urls:
            continue
        seen_urls.add(real_url)

        # Try to find a snippet near this result
        snippet = ""
        snippet_match = re.search(
            r'<h2[^>]*>.*?<a[^>]+href="' + re.escape(raw_href) + r'"[^>]*>.*?</a>.*?</h2>.*?<p>(.*?)</p>',
            html,
            re.DOTALL,
        )
        if snippet_match:
            snippet = _unescape(_strip_tags(snippet_match.group(1))).strip()

        lines.append(f"{title}\n  {real_url}\n  {snippet}")

    if not lines:
        return "No results found."

    return "\n\n".join(lines)
