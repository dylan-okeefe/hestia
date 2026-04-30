"""Tests for http_get SSRF protection."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from hestia.tools.builtin.http_get import SSRFSafeTransport, _is_url_safe


class TestSSRFProtection:
    """Tests for SSRF pre-flight check in http_get."""

    def test_blocks_non_http_schemes(self):
        """Test that non-HTTP schemes are blocked."""
        assert _is_url_safe("file:///etc/passwd") is not None
        assert _is_url_safe("ftp://example.com/file") is not None

    def test_allows_public_urls(self):
        """Test that public URLs pass pre-flight."""
        assert _is_url_safe("http://1.1.1.1/") is None
        assert _is_url_safe("https://93.184.216.34/") is None
        assert _is_url_safe("https://example.com/") is None

    def test_blocks_missing_scheme(self):
        """Test that URLs without scheme are blocked."""
        result = _is_url_safe("example.com/path")
        assert result is not None
        assert "scheme" in result.lower()

    def test_blocks_invalid_scheme(self):
        """Test that invalid schemes are blocked."""
        result = _is_url_safe("gopher://example.com/")
        assert result is not None
        assert "scheme" in result.lower()

    def test_requires_hostname(self):
        """Test that URLs without hostname are blocked."""
        result = _is_url_safe("http:///path")
        assert result is not None
        assert "hostname" in result.lower()


class TestHttpGetRedirectSSRF:
    """Tests for redirect-based SSRF via http_get."""

    @pytest.mark.asyncio
    async def test_ssrf_redirect_blocked(self):
        """A redirect to a private IP is blocked by the transport."""
        transport = SSRFSafeTransport()

        def _inner_handle(request: httpx.Request):
            if request.url.host == "example.com":
                # Return a redirect to the blocked metadata endpoint
                return httpx.Response(
                    302,
                    headers={"Location": "http://169.254.169.254/latest/meta-data/"},
                    request=request,
                )
            # Any other request should not reach here for the redirect target
            raise RuntimeError("Should not reach inner transport for blocked redirect")

        with patch.object(
            transport._inner, "handle_async_request", side_effect=_inner_handle
        ):
            async with httpx.AsyncClient(
                transport=transport, follow_redirects=True, timeout=5
            ) as client:
                with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
                    await client.get("http://example.com/redirect")


class TestSSRFSafeTransport:
    """Tests for SSRFSafeTransport at connection time."""

    @pytest.mark.asyncio
    async def test_transport_allows_public_ip(self):
        """Transport allows connections to public IPs."""
        transport = SSRFSafeTransport()
        mock_response = AsyncMock(spec=httpx.Response)

        with patch.object(
            transport._inner, "handle_async_request", return_value=mock_response
        ) as mock_handle:
            request = httpx.Request("GET", "http://1.1.1.1/")
            response = await transport.handle_async_request(request)
            assert response is mock_response
            mock_handle.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_transport_blocks_private_ip(self):
        """Transport blocks connections to private IPs."""
        transport = SSRFSafeTransport()

        blocked_urls = [
            "http://127.0.0.1/secret",
            "http://10.0.0.1/internal",
            "http://192.168.1.1/router",
            "http://172.16.0.1/internal",
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost/admin",
        ]

        for url in blocked_urls:
            request = httpx.Request("GET", url)
            with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
                await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_transport_blocks_dns_rebinding(self):
        """Transport blocks DNS rebinding by resolving at connection time."""
        transport = SSRFSafeTransport()

        with patch(
            "socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 0))]
        ):
            request = httpx.Request("GET", "http://evil.example.com/")
            with pytest.raises(httpx.ConnectError, match="SSRF blocked"):
                await transport.handle_async_request(request)
