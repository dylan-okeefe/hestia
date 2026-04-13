"""Tests for http_get SSRF protection."""

import pytest

from hestia.tools.builtin.http_get import _is_url_safe


class TestSSRFProtection:
    """Tests for SSRF protection in http_get."""

    def test_blocks_localhost(self):
        """Test that localhost is blocked."""
        assert _is_url_safe("http://localhost/admin") is not None
        assert "blocked range" in _is_url_safe("http://127.0.0.1/secret")

    def test_blocks_private_ranges(self):
        """Test that private IP ranges are blocked."""
        assert _is_url_safe("http://10.0.0.1/internal") is not None
        assert _is_url_safe("http://192.168.1.1/router") is not None
        assert _is_url_safe("http://172.16.0.1/internal") is not None

    def test_blocks_cloud_metadata(self):
        """Test that cloud metadata endpoint is blocked."""
        assert _is_url_safe("http://169.254.169.254/latest/meta-data/") is not None

    def test_blocks_non_http_schemes(self):
        """Test that non-HTTP schemes are blocked."""
        assert _is_url_safe("file:///etc/passwd") is not None
        assert _is_url_safe("ftp://example.com/file") is not None

    def test_allows_public_urls(self):
        """Test that public URLs are allowed."""
        # Only test URL parsing, not actual resolution
        # Public hostnames may fail in CI without network
        assert _is_url_safe("http://1.1.1.1/") is None
        assert _is_url_safe("https://93.184.216.34/") is None  # example.com IP

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
