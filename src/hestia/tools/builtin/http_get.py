"""HTTP GET tool with SSRF protection."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

from hestia.tools.builtin.memory_tools import current_session_id, current_trace_store
from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

logger = logging.getLogger(__name__)

# IP ranges that must never be fetched
_BLOCKED_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),         # current network
    ipaddress.ip_network("10.0.0.0/8"),         # private class A
    ipaddress.ip_network("127.0.0.0/8"),        # loopback
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),      # private class B
    ipaddress.ip_network("192.168.0.0/16"),     # private class C
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


class SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Transport that validates every connection target against blocked IP ranges.

    Prevents both redirect-based SSRF and DNS rebinding attacks by checking
    the resolved IP at connection time, not at request time.
    """

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        if hostname:
            # Resolve at connection time — same lookup httpx will use
            try:
                addr_info = socket.getaddrinfo(str(hostname), None)
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


@tool(
    name="http_get",
    public_description="Fetch the contents of a URL via HTTP GET.",
    max_inline_chars=6000,
    tags=["network", "builtin"],
    capabilities=[NETWORK_EGRESS],
)
async def http_get(url: str, timeout_seconds: int = 30) -> str:
    """Fetch a URL and return its text content.

    Returns the response body as text, capped by the tool's max_inline_chars.
    Large responses are automatically promoted to artifacts by the registry.
    Blocks requests to private/internal IP ranges for SSRF protection.
    """
    # SSRF pre-flight check (user-friendly errors)
    if error := _is_url_safe(url):
        return error

    async with httpx.AsyncClient(
        transport=SSRFSafeTransport(),
        follow_redirects=True,
        timeout=timeout_seconds,
    ) as client:
        response = await client.get(url)
        await _record_egress(str(response.url), response.status_code, len(response.content))
        response.raise_for_status()
        return response.text


async def _record_egress(url: str, status: int, size: int) -> None:
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
            logger.debug("Failed to record egress event", exc_info=True)
