"""Indeed job-search tool for A-IN-1 and other Indeed lookups."""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any

from hestia.tools.builtin.http_get import _http_get_impl
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)


_VARIATIONS = [
    'window.mosaic.providerData["mosaic-provider-jobcards"]',
    "window.mosaic.providerData['mosaic-provider-jobcards']",
]


def _extract_js_object(text: str, variable: str) -> dict[str, Any] | None:
    """Extract the JSON object assigned to *variable* in *text*.

    Uses brace counting so nested objects/strings are handled regardless of
    where the statement ends.
    """
    idx = text.find(variable)
    if idx == -1:
        return None

    start = idx + len(variable)
    while start < len(text) and text[start] in "= \t":
        start += 1

    depth = 0
    in_str = False
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
        i += 1

    obj_str = text[start:i]
    try:
        return json.loads(obj_str)
    except json.JSONDecodeError as exc:
        logger.debug("Could not parse Indeed jobcards JSON: %s", exc)
        return None


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _indeed_results(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Pull job cards out of the parsed providerData object."""
    for path in (
        ("metaData", "mosaicProviderJobCardsModel", "results"),
        ("mosaicProviderJobCardsModel", "results"),
    ):
        node = data
        for key in path:
            if not isinstance(node, dict):
                break
            node = node.get(key)
        if isinstance(node, list):
            return node[:limit]
    return []


@tool(
    name="indeed_search_jobs",
    public_description=(
        "Search Indeed.com for jobs and return a concise Markdown list. "
        "Use this for A-IN-1 (Indeed) job searches. It fetches with Chrome "
        "TLS/HTTP fingerprint impersonation and extracts job cards automatically."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Job keywords (e.g. 'agentic AI engineer').",
            },
            "location": {
                "type": "string",
                "description": "Location (e.g. 'United States', 'Remote', 'New York, NY').",
                "default": "United States",
            },
            "fromage": {
                "type": "integer",
                "description": "Maximum age of postings in days.",
                "default": 7,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of jobs to return (default 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
    max_inline_chars=12000,
    tags=["network", "builtin", "jobs"],
    capabilities=[NETWORK_EGRESS],
)
async def indeed_search_jobs(
    query: str,
    location: str = "United States",
    fromage: int = 7,
    limit: int = 10,
) -> str:
    """Search Indeed and return a concise Markdown job list."""
    params = {
        "q": query,
        "l": location,
        "fromage": str(fromage),
        "sort": "date",
    }
    url = "https://www.indeed.com/jobs?" + urllib.parse.urlencode(params)

    try:
        page = await _http_get_impl(
            url,
            timeout_seconds=45,
            use_curl_cffi=True,
            curl_cffi_fallback=True,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Indeed fetch failed: {exc}"

    if page.startswith(("http_get", "curl_cffi fetch failed", "SSRF blocked")) or len(page) < 1000:
        return (
            "Could not retrieve Indeed results. The site may be blocking the request "
            f"or returned an error. First bytes: {page[:500]}"
        )

    data: dict[str, Any] | None = None
    for variable in _VARIATIONS:
        data = _extract_js_object(page, variable)
        if data is not None:
            break

    if data is None:
        return (
            "Could not extract job listings from Indeed. The page structure may have "
            "changed, or the request was blocked. Try a more specific query or use "
            "browser_get with headed mode if login is required."
        )

    jobs = _indeed_results(data, max(limit, 1))
    if not jobs:
        return "No job listings found for that query/location."

    lines: list[str] = [f"# Indeed results for \"{query}\"\n"]
    for job in jobs:
        title = job.get("displayTitle") or job.get("title") or "Untitled"
        company = job.get("company") or "Unknown company"
        loc = job.get("formattedLocation") or "Location not listed"
        posted = job.get("formattedRelativeTime") or ""
        salary = ""
        salary_snippet = job.get("salarySnippet")
        if isinstance(salary_snippet, dict):
            salary = salary_snippet.get("text") or ""
        snippet = _strip_html(job.get("snippet"))
        jobkey = job.get("jobkey")
        link = f"https://www.indeed.com/viewjob?jk={jobkey}" if jobkey else ""

        lines.append(f"## {title}")
        lines.append(f"- **Company:** {company}")
        lines.append(f"- **Location:** {loc}")
        if posted:
            lines.append(f"- **Posted:** {posted}")
        if salary:
            lines.append(f"- **Salary:** {salary}")
        if snippet:
            lines.append(f"- **Snippet:** {snippet}")
        if link:
            lines.append(f"- **Link:** {link}")
        lines.append("")

    return "\n".join(lines)
