"""Unit tests for new built-in tools (write_file, list_dir, http_get)."""

import asyncio
import socket
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from hestia.tools.builtin.http_get import SSRFSafeTransport, _is_url_safe, http_get
from hestia.config import StorageConfig
from hestia.tools.builtin.list_dir import make_list_dir_tool
from hestia.tools.builtin.write_file import make_write_file_tool


class TestWriteFile:
    """Tests for write_file tool."""

    @pytest.mark.asyncio
    async def test_write_file_creates_file(self, tmp_path):
        """Can write content to a file."""
        write_file = make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        target = tmp_path / "test.txt"
        result = await write_file(str(target), "Hello, world!")

        assert target.exists()
        assert target.read_text() == "Hello, world!"
        assert "13 bytes" in result

    @pytest.mark.asyncio
    async def test_write_file_creates_parent_dirs(self, tmp_path):
        """Creates parent directories if they don't exist."""
        write_file = make_write_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        target = tmp_path / "nested" / "deep" / "file.txt"
        result = await write_file(str(target), "Nested content")

        assert target.exists()
        assert target.read_text() == "Nested content"


class TestListDir:
    """Tests for list_dir tool."""

    @pytest.mark.asyncio
    async def test_list_dir_shows_files(self, tmp_path):
        """Lists files in a directory."""
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()

        result = await list_dir(str(tmp_path))

        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "[dir] subdir" in result
        assert "(empty)" not in result

    @pytest.mark.asyncio
    async def test_list_dir_caps_at_max_entries(self, tmp_path):
        """Caps output at max_entries."""
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        # Create 10 files
        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text("x")

        result = await list_dir(str(tmp_path), max_entries=5)

        assert "more entries" in result

    @pytest.mark.asyncio
    async def test_list_dir_nonexistent_returns_error(self, tmp_path):
        """Returns error for non-existent directory."""
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        result = await list_dir(str(tmp_path / "does_not_exist"))

        assert "Error:" in result
        assert "is not a directory" in result

    @pytest.mark.asyncio
    async def test_list_dir_empty(self, tmp_path):
        """Shows empty for empty directory."""
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        result = await list_dir(str(tmp_path))

        assert "(empty)" in result

    @pytest.mark.asyncio
    async def test_list_dir_overflow_count_is_correct(self, tmp_path):
        """Overflow message shows correct remaining count."""
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        for i in range(10):
            (tmp_path / f"file{i:02d}.txt").write_text("x")

        result = await list_dir(str(tmp_path), max_entries=3)

        assert "7 more entries" in result


class TestHttpGet:
    """Tests for http_get tool."""

    @pytest.mark.asyncio
    async def test_http_get_fetches_url(self):
        """Can fetch a URL and return text content."""
        mock_response = AsyncMock()
        mock_response.text = "Test response content"
        mock_response.raise_for_status = lambda: None  # sync method

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await http_get("http://1.1.1.1/test")

        assert result == "Test response content"
        mock_client.get.assert_called_once_with("http://1.1.1.1/test")

    def test_preflight_blocks_invalid_schemes(self):
        """Pre-flight check blocks invalid schemes and missing hostnames."""
        assert _is_url_safe("file:///etc/passwd") is not None
        assert _is_url_safe("ftp://example.com/file") is not None
        assert _is_url_safe("example.com/path") is not None
        assert _is_url_safe("http:///path") is not None

    def test_preflight_allows_public_and_private_hostnames(self):
        """Pre-flight allows all valid HTTP(S) URLs; transport blocks private IPs."""
        assert _is_url_safe("http://1.1.1.1/") is None
        assert _is_url_safe("https://93.184.216.34/") is None
        assert _is_url_safe("http://127.0.0.1/secret") is None

    @pytest.mark.asyncio
    async def test_transport_uses_asyncio_to_thread_for_getaddrinfo(self):
        """SSRFSafeTransport calls socket.getaddrinfo via asyncio.to_thread."""
        transport = SSRFSafeTransport()
        request = httpx.Request("GET", "http://example.com/")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
            ]
            # We need the inner transport to not actually make a request
            with patch.object(transport._inner, "handle_async_request", new_callable=AsyncMock) as mock_inner:
                mock_inner.return_value = httpx.Response(200, text="ok")
                await transport.handle_async_request(request)

        mock_to_thread.assert_awaited_once()
        assert mock_to_thread.call_args[0][0] == socket.getaddrinfo
        assert mock_to_thread.call_args[0][1] == "example.com"
