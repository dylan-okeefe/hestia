"""Unit tests for new built-in tools (write_file, list_dir, http_get)."""

from unittest.mock import AsyncMock, patch

import pytest

from hestia.tools.builtin.http_get import http_get
from hestia.tools.builtin.list_dir import list_dir
from hestia.tools.builtin.write_file import write_file


class TestWriteFile:
    """Tests for write_file tool."""

    @pytest.mark.asyncio
    async def test_write_file_creates_file(self, tmp_path):
        """Can write content to a file."""
        target = tmp_path / "test.txt"
        result = await write_file(str(target), "Hello, world!")

        assert target.exists()
        assert target.read_text() == "Hello, world!"
        assert "13 bytes" in result

    @pytest.mark.asyncio
    async def test_write_file_creates_parent_dirs(self, tmp_path):
        """Creates parent directories if they don't exist."""
        target = tmp_path / "nested" / "deep" / "file.txt"
        result = await write_file(str(target), "Nested content")

        assert target.exists()
        assert target.read_text() == "Nested content"


class TestListDir:
    """Tests for list_dir tool."""

    @pytest.mark.asyncio
    async def test_list_dir_shows_files(self, tmp_path):
        """Lists files in a directory."""
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
        # Create 10 files
        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text("x")

        result = await list_dir(str(tmp_path), max_entries=5)

        assert "more entries" in result

    @pytest.mark.asyncio
    async def test_list_dir_nonexistent_returns_error(self, tmp_path):
        """Returns error for non-existent directory."""
        result = await list_dir(str(tmp_path / "does_not_exist"))

        assert "Error:" in result
        assert "is not a directory" in result

    @pytest.mark.asyncio
    async def test_list_dir_empty(self, tmp_path):
        """Shows empty for empty directory."""
        result = await list_dir(str(tmp_path))

        assert "(empty)" in result


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
            result = await http_get("http://example.com/test")

        assert result == "Test response content"
        mock_client.get.assert_called_once_with("http://example.com/test")
