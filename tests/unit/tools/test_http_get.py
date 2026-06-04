"""Tests for http_get SSRF protection."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hestia.tools.builtin.http_get import _BLOCKED_RANGES, SSRFSafeTransport


@pytest.mark.asyncio
async def test_ssrf_transport_blocks_ipv6_loopback():
    """IPv6 loopback (::1) is blocked by SSRFSafeTransport."""
    transport = SSRFSafeTransport()
    request = httpx.Request("GET", "http://example.com")

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, 0, 0, "", ("::1", 0))],
    ), pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_ssrf_transport_blocks_ipv6_link_local():
    """IPv6 link-local (fe80::) is blocked by SSRFSafeTransport."""
    transport = SSRFSafeTransport()
    request = httpx.Request("GET", "http://example.com")

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, 0, 0, "", ("fe80::1", 0))],
    ), pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_ssrf_transport_blocks_ipv6_unique_local():
    """IPv6 unique-local (fc00::) is blocked by SSRFSafeTransport."""
    transport = SSRFSafeTransport()
    request = httpx.Request("GET", "http://example.com")

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, 0, 0, "", ("fc00::1", 0))],
    ), pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_ssrf_transport_allows_public_ipv6():
    """Public IPv6 is allowed by SSRFSafeTransport."""
    transport = SSRFSafeTransport()
    request = httpx.Request("GET", "http://example.com")

    mock_inner = AsyncMock()
    transport._inner = mock_inner
    mock_inner.handle_async_request.return_value = MagicMock(spec=httpx.Response)

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, 0, 0, "", ("2001:4860:4860::8888", 0))],
    ):
        await transport.handle_async_request(request)

    mock_inner.handle_async_request.assert_awaited_once_with(request)


def test_blocked_ranges_include_ipv6():
    """_BLOCKED_RANGES includes the expected IPv6 networks."""
    import ipaddress

    networks = [str(n) for n in _BLOCKED_RANGES]
    assert "::1/128" in networks
    assert "fc00::/7" in networks
    assert "fe80::/10" in networks
    assert ipaddress.ip_address("::1") in ipaddress.ip_network("::1/128")
    assert ipaddress.ip_address("fe80::1") in ipaddress.ip_network("fe80::/10")
    assert ipaddress.ip_address("fc00::1") in ipaddress.ip_network("fc00::/7")


@pytest.mark.asyncio
async def test_ssrf_transport_blocks_ipv4_mapped_ipv6_loopback():
    """IPv4-mapped IPv6 loopback (::ffff:127.0.0.1) is blocked."""
    transport = SSRFSafeTransport()
    request = httpx.Request("GET", "http://example.com")

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, 0, 0, "", ("::ffff:127.0.0.1", 0))],
    ), pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)


@pytest.mark.asyncio
async def test_ssrf_transport_blocks_ipv4_mapped_ipv6_metadata():
    """IPv4-mapped IPv6 metadata endpoint (::ffff:169.254.169.254) is blocked."""
    transport = SSRFSafeTransport()
    request = httpx.Request("GET", "http://example.com")

    with patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET6, 0, 0, "", ("::ffff:169.254.169.254", 0))],
    ), pytest.raises(httpx.ConnectError, match="SSRF blocked"):
        await transport.handle_async_request(request)
