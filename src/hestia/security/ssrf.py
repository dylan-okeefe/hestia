"""Shared SSRF protection helpers for URL and IP validation."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

#: IPv4 ranges that must never be fetched by browser/http tools.
_BLOCKED_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("169.254.169.254/32"),  # cloud metadata
    ipaddress.ip_network("10.0.0.0/8"),  # RFC1918 private class A
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918 private class B
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 private class C
]


class SSRFBlockedError(Exception):
    """Raised when a URL or resolved IP is blocked for SSRF protection."""


def _assert_ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Raise ``SSRFBlockedError`` if *ip* is not a globally reachable unicast address.

    IPv4-mapped IPv6 addresses are normalized to their IPv4 form before checking.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if not ip.is_global:
        raise SSRFBlockedError(f"{ip} is not globally unicast")

    for blocked in _BLOCKED_RANGES:
        if ip in blocked:
            raise SSRFBlockedError(f"{ip} is in {blocked}")


async def assert_url_safe(url: str) -> None:
    """Parse *url*, enforce an http(s) scheme, and validate resolved IPs.

    Raises:
        SSRFBlockedError: If the scheme is unsupported, the hostname cannot be
            resolved, or any resolved IP is blocked.
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise SSRFBlockedError(f"Invalid URL: {url}") from exc

    if not parsed.scheme:
        raise SSRFBlockedError(
            f"Missing URL scheme (use http:// or https://): {url}"
        )

    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(
            f"Unsupported scheme '{parsed.scheme}' — only http and https are allowed"
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError(f"No hostname in URL: {url}")

    try:
        addr_info = await asyncio.get_running_loop().getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Cannot resolve hostname: {hostname}") from exc

    for _family, _type, _proto, _canonical, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        try:
            _assert_ip_allowed(ip)
        except SSRFBlockedError as exc:
            raise SSRFBlockedError(
                f"SSRF blocked: {hostname} resolves to {ip} ({exc})"
            ) from exc



