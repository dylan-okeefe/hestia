"""HTTP GET tool with SSRF protection."""

import ipaddress
import socket
from urllib.parse import urlparse

from hestia.tools.capabilities import NETWORK_EGRESS
from hestia.tools.metadata import tool

# IP ranges that must never be fetched
_BLOCKED_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),         # private class A
    ipaddress.ip_network("172.16.0.0/12"),      # private class B
    ipaddress.ip_network("192.168.0.0/16"),     # private class C
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


def _is_url_safe(url: str) -> str | None:
    """Check if a URL is safe to fetch.

    Returns an error message if blocked, None if safe.
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

    # Resolve hostname to IP and check against blocked ranges
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return f"Cannot resolve hostname: {hostname}"

    for _family, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        for blocked in _BLOCKED_RANGES:
            if ip in blocked:
                return f"Access denied: {hostname} resolves to blocked range ({blocked})"

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
    # SSRF check
    if error := _is_url_safe(url):
        return error

    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
