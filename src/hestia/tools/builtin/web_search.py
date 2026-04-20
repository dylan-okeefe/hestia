"""Web search tool with pluggable providers.

The tool is a factory — the CLI only registers it if WebSearchConfig is
populated. The function-level signature is provider-agnostic; provider
selection happens inside the factory based on config.
"""

from __future__ import annotations

from typing import Any

import httpx

from hestia.config import WebSearchConfig
from hestia.tools.builtin.http_get import SSRFSafeTransport
from hestia.tools.builtin.memory_tools import current_session_id, current_trace_store
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool


class WebSearchError(RuntimeError):
    """Raised when the configured provider fails."""


async def _tavily_search(
    query: str,
    *,
    api_key: str,
    max_results: int,
    include_raw_content: bool,
    search_depth: str,
    time_range: str | None,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    # Copilot H-4: send the API key as ``Authorization: Bearer ...``
    # instead of embedding it in the request body. The body ends up in
    # proxy/HTTP-debug logs (including httpx's own DEBUG logs) and any
    # outbound SIEM that captures request payloads; the Authorization
    # header is conventionally redacted. Tavily accepts both forms.
    payload: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_raw_content": include_raw_content,
    }
    if time_range is not None:
        payload["time_range"] = time_range

    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(
        transport=SSRFSafeTransport(),
        follow_redirects=True,
        timeout=timeout_seconds,
    ) as client:
        response = await client.post(
            "https://api.tavily.com/search", json=payload, headers=headers
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            await _record_egress(str(exc.request.url), exc.response.status_code if exc.response else None, 0)
            raise WebSearchError(
                f"Tavily request failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        await _record_egress(str(response.url), response.status_code, len(response.content))
        data = response.json()

    results = data.get("results") or []
    if not isinstance(results, list):
        raise WebSearchError("Tavily returned malformed response (no 'results' list)")
    return results


def _format_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No results."
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(untitled)")
        url = r.get("url", "(no url)")
        snippet = (r.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:500].rstrip() + "..."
        lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
    return "\n\n".join(lines)


def make_web_search_tool(config: WebSearchConfig) -> Any:
    """Build the web_search tool bound to the configured provider.

    Returns None if config.provider is empty or config.api_key is missing —
    caller should not register a None tool.
    """
    if not config.provider or not config.api_key:
        return None

    if config.provider != "tavily":
        raise ValueError(
            f"Unsupported web_search provider: {config.provider!r} "
            "(only 'tavily' is currently wired)"
        )

    @tool(
        name="web_search",
        public_description=(
            "Search the web via the configured provider. Returns top results "
            "with title, URL, and snippet. Use this to find current information "
            "when you don't already have a specific URL to fetch."
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
                    "description": (
                        "How many results to return. Default from config "
                        f"({config.max_results})."
                    ),
                },
                "time_range": {
                    "type": "string",
                    "description": (
                        "Restrict to a recency window: 'day', 'week', 'month', or 'year'. "
                        "Omit for any time."
                    ),
                },
            },
            "required": ["query"],
        },
        max_inline_chars=6000,
        tags=["network", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def web_search(
        query: str,
        max_results: int | None = None,
        time_range: str | None = None,
    ) -> str:
        """Run a web search via the configured provider."""
        effective_max = max_results if max_results is not None else config.max_results
        effective_time = time_range if time_range is not None else config.time_range
        try:
            results = await _tavily_search(
                query,
                api_key=config.api_key,
                max_results=effective_max,
                include_raw_content=config.include_raw_content,
                search_depth=config.search_depth,
                time_range=effective_time,
                timeout_seconds=30,
            )
        except WebSearchError as exc:
            return f"Web search failed: {exc}"
        except httpx.HTTPError as exc:
            return f"Web search transport error: {type(exc).__name__}: {exc}"
        return _format_results(results)

    return web_search


async def _record_egress(url: str, status: int | None, size: int) -> None:
    """Best-effort egress logging via the current trace store."""
    trace_store = current_trace_store.get()
    session_id = current_session_id.get()
    if trace_store is not None and session_id is not None:
        try:
            await trace_store.record_egress(
                session_id=session_id,
                url=url,
                status=status,
                size=size,
            )
        except Exception:
            pass
