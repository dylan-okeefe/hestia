"""HTTP GET tool with SSRF protection."""

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from hestia.runtime_context import current_session_id, current_trace_store
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)

# Optional curl_cffi for sites that block based on TLS/HTTP fingerprints.
try:
    from curl_cffi.requests import AsyncSession as CurlCffiSession

    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False

# IP ranges that must never be fetched
_BLOCKED_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),  # current network
    ipaddress.ip_network("10.0.0.0/8"),  # private class A
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),  # private class B
    ipaddress.ip_network("192.168.0.0/16"),  # private class C
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


class SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Transport that validates every connection target against blocked IP ranges.

    Prevents redirect-based SSRF by checking the resolved IP at connection
    time. Does not fully mitigate DNS rebinding (``getaddrinfo`` and
    ``httpx`` may perform separate lookups).
    """

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        if hostname:
            # Resolve at connection time — same lookup httpx will use
            try:
                addr_info = await asyncio.to_thread(socket.getaddrinfo, str(hostname), None)
            except socket.gaierror as exc:
                raise httpx.ConnectError(f"Cannot resolve hostname: {hostname}") from exc

            for _family, _, _, _, sockaddr in addr_info:
                ip = ipaddress.ip_address(sockaddr[0])
                for blocked in _BLOCKED_RANGES:
                    if ip in blocked:
                        raise httpx.ConnectError(
                            f"SSRF blocked: {hostname} resolves to {ip} (in {blocked})"
                        )

        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def _is_url_safe(url: str) -> str | None:
    """Check if a URL is safe to fetch.

    Returns an error message if blocked, None if safe.
    This is a fast pre-flight check for user-friendly errors only.
    The actual security boundary is SSRFSafeTransport.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return f"Invalid URL: {url}"

    if not parsed.scheme:
        return f"Missing URL scheme (use http:// or https://): {url}"

    if parsed.scheme not in ("http", "https"):
        return f"Unsupported scheme '{parsed.scheme}' — only http and https are allowed"

    hostname = parsed.hostname
    if not hostname:
        return f"No hostname in URL: {url}"

    return None


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def _fetch_with_httpx(url: str, timeout_seconds: int) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=SSRFSafeTransport(),
        follow_redirects=True,
        timeout=timeout_seconds,
        headers=_BROWSER_HEADERS,
    ) as client:
        return await client.get(url)


async def _fetch_with_curl_cffi(url: str, timeout_seconds: int) -> str:
    """Fetch using curl_cffi with browser TLS/HTTP fingerprint impersonation.

    curl_cffi does not support custom transports, so SSRF protection here is
    limited to the pre-flight ``_is_url_safe`` check and manual redirect
    validation. This is a best-effort fallback for sites that block based on
    fingerprints rather than IP-based access control.
    """
    # Pre-flight already done by caller; manual redirect loop for safety.
    current_url = url
    redirects = 0
    max_redirects = 10

    async with CurlCffiSession() as session:
        while redirects < max_redirects:
            response = await session.get(
                current_url,
                headers=_BROWSER_HEADERS,
                timeout=timeout_seconds,
                allow_redirects=False,
                impersonate="chrome131",
            )
            await _record_egress(
                str(current_url), response.status_code, len(response.content)
            )

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise RuntimeError(
                        f"Redirect response {response.status_code} without Location header"
                    )
                # Resolve relative redirects
                from urllib.parse import urljoin

                current_url = urljoin(current_url, location)
                if error := _is_url_safe(current_url):
                    raise RuntimeError(f"SSRF blocked redirect: {error}")
                redirects += 1
                continue

            response.raise_for_status()
            return str(response.text)

    raise RuntimeError(f"Too many redirects (>{max_redirects})")


async def _http_get_impl(url: str, timeout_seconds: int, use_curl_cffi: bool) -> str:
    """Fetch a URL and return its text content."""
    # SSRF pre-flight check (user-friendly errors)
    if error := _is_url_safe(url):
        return error

    response = await _fetch_with_httpx(url, timeout_seconds)
    await _record_egress(str(response.url), response.status_code, len(response.content))

    if response.status_code == 403 and use_curl_cffi and _CURL_CFFI_AVAILABLE:
        logger.debug("HTTP 403 from %s; retrying with curl_cffi impersonation", url)
        try:
            return await _fetch_with_curl_cffi(url, timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — tool boundary
            logger.debug("curl_cffi fallback failed: %s", exc)
            # Fall through to return the original 403 error

    response.raise_for_status()
    return response.text


@tool(
    name="http_get",
    public_description=(
        "Fetch any web page or API via HTTP GET. Use this for reading pages, "
        "calling REST APIs, or searching via raw-HTML-friendly engines like "
        "DuckDuckGo (html.duckduckgo.com/html/?q=...). DOES NOT work on "
        "JavaScript-heavy sites like Google Search, Google Maps, or Yelp. "
        "For general web searches, use the search_web tool instead. "
        "Params: url (str), timeout_seconds (int, default 30)."
    ),
    max_inline_chars=6000,
    tags=["network", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def http_get(url: str, timeout_seconds: int = 30) -> str:
    """Fetch a URL and return its text content.

    Returns the response body as text, capped by the tool's max_inline_chars.
    Large responses are automatically promoted to artifacts by the registry.
    Blocks requests to private/internal IP ranges for SSRF protection.

    The curl_cffi fallback (browser TLS/HTTP fingerprint impersonation) is only
    used when ``config.use_curl_cffi_fallback`` is explicitly enabled.
    """
    return await _http_get_impl(url, timeout_seconds, use_curl_cffi=False)


def make_http_get_tool(use_curl_cffi_fallback: bool = False) -> Callable[..., Any]:
    """Factory for http_get with configurable curl_cffi fallback."""

    @tool(
        name="http_get",
        public_description=(
            "Fetch any web page or API via HTTP GET. Use this for reading pages, "
            "calling REST APIs, or searching via raw-HTML-friendly engines like "
            "DuckDuckGo (html.duckduckgo.com/html/?q=...). DOES NOT work on "
            "JavaScript-heavy sites like Google Search, Google Maps, or Yelp. "
            "For general web searches, use the search_web tool instead. "
            "Params: url (str), timeout_seconds (int, default 30)."
        ),
        max_inline_chars=6000,
        tags=["network", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def http_get(url: str, timeout_seconds: int = 30) -> str:
        """Fetch a URL and return its text content."""
        return await _http_get_impl(url, timeout_seconds, use_curl_cffi=use_curl_cffi_fallback)

    return http_get


async def _record_egress(url: str, status: int, size: int) -> None:
    """Best-effort egress logging via the current trace store.

    Query parameters are stripped before storage to avoid persisting
    API keys or tokens that may appear in URLs.
    """
    from urllib.parse import urlparse, urlunparse

    trace_store = current_trace_store.get()
    session_id = current_session_id.get()
    if trace_store is not None and session_id is not None:
        try:
            parsed = urlparse(url)
            safe_url = urlunparse(parsed._replace(query="", fragment=""))
            await trace_store.record_egress(
                session_id=session_id,
                url=safe_url,
                status=status,
                size=size,
            )
        except Exception:  # noqa: BLE001
            # Egress audit is best-effort; never fail the tool call because of it.
            logger.warning("Failed to record egress event", exc_info=True)
