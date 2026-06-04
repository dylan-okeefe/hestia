"""Unit tests for built-in tools."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.config import StorageConfig
from hestia.tools.builtin.current_time import current_time
from hestia.tools.builtin.edit_file import make_edit_file_tool
from hestia.tools.builtin.glob import make_glob_tool
from hestia.tools.builtin.grep import make_grep_tool
from hestia.tools.builtin.http_get import SSRFSafeTransport, _is_url_safe, http_get
from hestia.tools.builtin.list_dir import make_list_dir_tool
from hestia.tools.builtin.read_artifact import make_read_artifact_tool
from hestia.tools.builtin.read_file import make_read_file_tool
from hestia.tools.builtin.terminal import make_terminal_tool
from hestia.tools.builtin.write_file import make_write_file_tool


class TestCurrentTime:
    """Tests for current_time tool."""

    @pytest.mark.asyncio
    async def test_returns_datetime_string_utc(self):
        """Returns a datetime string in UTC by default."""
        result = await current_time()
        # Should be parseable format
        assert len(result) > 10
        assert result.count(":") >= 2  # Has time component
        assert "UTC" in result or len(result) == 25  # UTC or offset format

    @pytest.mark.asyncio
    async def test_valid_timezone(self):
        """Returns time for valid timezone."""
        result = await current_time("America/New_York")
        assert "Unknown" not in result
        assert "EST" in result or "EDT" in result or len(result) > 15

    @pytest.mark.asyncio
    async def test_invalid_timezone_error_message(self):
        """Invalid timezone returns error message, not exception."""
        result = await current_time("NotARealTimezone")
        assert "Unknown" in result
        assert "IANA" in result


class TestReadFile:
    """Tests for read_file tool."""

    @pytest.mark.asyncio
    async def test_missing_file(self, tmp_path):
        """Missing file returns error message."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        result = await read_file("/nonexistent/path/to/file.txt")
        assert "Access denied" in result or "File not found" in result

    @pytest.mark.asyncio
    async def test_directory_not_file(self, tmp_path):
        """Directory returns error message."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=["/tmp"]))
        result = await read_file("/tmp")
        assert "Not a file" in result

    @pytest.mark.asyncio
    async def test_reads_text_file(self, tmp_path):
        """Reads text file contents."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = await read_file(str(test_file))
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_reads_utf8_content(self, tmp_path):
        """Reads UTF-8 content correctly."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("Hello 世界 🌍", encoding="utf-8")

        result = await read_file(str(test_file))
        assert "世界" in result
        assert "🌍" in result

    @pytest.mark.asyncio
    async def test_respects_max_bytes(self, tmp_path):
        """Respects max_bytes parameter."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        test_file = tmp_path / "large.txt"
        test_file.write_text("x" * 10000)

        result = await read_file(str(test_file), max_bytes=100)
        assert len(result) == 100

    @pytest.mark.asyncio
    async def test_binary_file_message(self, tmp_path):
        """Binary files return message, not decoded content."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(bytes(range(256)))  # Non-UTF8 bytes

        result = await read_file(str(test_file))
        assert "Binary file" in result


class TestEditFile:
    """Tests for edit_file tool."""

    @pytest.mark.asyncio
    async def test_edit_file_exact_match_once(self, tmp_path):
        """Exact match once → success with diff preview."""
        edit_file = make_edit_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        target = tmp_path / "test.txt"
        target.write_text("hello world")

        result = await edit_file(str(target), "hello world", "hello universe")

        assert target.read_text() == "hello universe"
        assert "Edited" in result
        assert "- hello world" in result
        assert "+ hello universe" in result

    @pytest.mark.asyncio
    async def test_edit_file_zero_matches(self, tmp_path):
        """Zero matches → error."""
        edit_file = make_edit_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        target = tmp_path / "test.txt"
        target.write_text("hello world")

        result = await edit_file(str(target), "not present", "replacement")

        assert "Error:" in result
        assert "not found" in result
        assert target.read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_edit_file_multiple_matches(self, tmp_path):
        """Multiple matches → error."""
        edit_file = make_edit_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        target = tmp_path / "test.txt"
        target.write_text("abc abc abc")

        result = await edit_file(str(target), "abc", "xyz")

        assert "Error:" in result
        assert "found 3 occurrences" in result
        assert target.read_text() == "abc abc abc"

    @pytest.mark.asyncio
    async def test_edit_file_missing_file(self, tmp_path):
        """File does not exist → error."""
        edit_file = make_edit_file_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        target = tmp_path / "missing.txt"

        result = await edit_file(str(target), "old", "new")

        assert "File not found" in result


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
        await write_file(str(target), "Nested content")

        assert target.exists()
        assert target.read_text() == "Nested content"

    @pytest.mark.asyncio
    async def test_write_guard_blocks_existing_file(self, tmp_path):
        """write_file on existing path → error with edit_file hint."""
        write_file = make_write_file_tool(
            StorageConfig(allowed_roots=[str(tmp_path)]), write_guard_enabled=True
        )
        target = tmp_path / "existing.txt"
        target.write_text("original")

        result = await write_file(str(target), "new content")

        assert "already exists" in result
        assert "edit_file(path=..., old_string=..., new_string=...)" in result
        assert target.read_text() == "original"

    @pytest.mark.asyncio
    async def test_write_guard_disabled_allows_overwrite(self, tmp_path):
        """write_guard disabled → allows overwrite."""
        write_file = make_write_file_tool(
            StorageConfig(allowed_roots=[str(tmp_path)]), write_guard_enabled=False
        )
        target = tmp_path / "existing.txt"
        target.write_text("original")

        result = await write_file(str(target), "new content")

        assert target.read_text() == "new content"
        assert "new content" in result or "bytes" in result


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


class TestReadArtifact:
    """Tests for read_artifact tool."""

    @pytest.mark.asyncio
    async def test_reads_existing_artifact(self, tmp_path):
        """Reads content of existing artifact."""
        store = ArtifactStore(root=tmp_path)
        handle = store.store(b"artifact content", source_tool="test")

        read_tool = make_read_artifact_tool(store)
        result = await read_tool(handle)
        assert result == "artifact content"

    @pytest.mark.asyncio
    async def test_missing_artifact(self, tmp_path):
        """Missing artifact returns error message."""
        store = ArtifactStore(root=tmp_path)
        read_tool = make_read_artifact_tool(store)

        result = await read_tool("art_nonexistent")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_expired_artifact(self, tmp_path):
        """Expired artifact returns error message."""
        store = ArtifactStore(root=tmp_path)
        handle = store.store(b"expires", ttl=0)  # Already expired

        read_tool = make_read_artifact_tool(store)
        result = await read_tool(handle)
        assert "expired" in result or "not found" in result


class TestTerminal:
    """Tests for terminal tool."""

    @pytest.fixture
    def terminal(self):
        return make_terminal_tool()

    @pytest.mark.asyncio
    async def test_echo_command(self, terminal):
        """echo command returns stdout."""
        result = await terminal("echo hello")
        assert "exit_code: 0" in result
        assert "hello" in result
        assert "--- stdout ---" in result

    @pytest.mark.asyncio
    async def test_stderr_captured(self, terminal):
        """stderr is captured and returned."""
        result = await terminal("echo error >&2")
        assert "--- stderr ---" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, terminal):
        """Non-zero exit code is reported."""
        result = await terminal("exit 42")
        assert "exit_code: 42" in result

    @pytest.mark.asyncio
    async def test_timeout(self, terminal):
        """Timeout is respected."""
        result = await terminal("sleep 5", timeout=0.5)
        assert "TIMEOUT" in result
        assert "0.5s" in result

    @pytest.mark.asyncio
    async def test_list_directory(self, terminal):
        """Can list directory contents."""
        result = await terminal("ls /tmp")
        assert "exit_code: 0" in result
        # /tmp should have something in it on most systems
        assert len(result) > len("exit_code: 0\n--- stdout ---\n")

    @pytest.mark.asyncio
    async def test_blocked_pattern_rejects_command(self):
        """Commands matching blocked patterns are rejected without execution."""
        terminal = make_terminal_tool([r"rm\s+-rf\s+/"])
        result = await terminal("rm -rf /")
        assert "BLOCKED" in result

    @pytest.mark.asyncio
    async def test_non_blocked_command_runs(self):
        """Commands not matching blocked patterns execute normally."""
        terminal = make_terminal_tool([r"rm\s+-rf\s+/"])
        result = await terminal("echo hello")
        assert "BLOCKED" not in result
        assert "hello" in result


class TestGlob:
    """Tests for glob tool."""

    @pytest.mark.asyncio
    async def test_glob_returns_matching_files(self, tmp_path):
        """glob returns files matching pattern."""
        glob = make_glob_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("x")
        (tmp_path / "c.txt").write_text("x")

        result = await glob("*.py", str(tmp_path))

        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, tmp_path):
        """glob returns message when no matches."""
        glob = make_glob_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        result = await glob("*.nomatch", str(tmp_path))
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_glob_truncation(self, tmp_path):
        """glob truncates when results exceed limit."""
        glob = make_glob_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        for i in range(105):
            (tmp_path / f"file{i:03d}.py").write_text("x")

        result = await glob("*.py", str(tmp_path))

        assert "truncated" in result


class TestGrep:
    """Tests for grep tool."""

    @pytest.mark.asyncio
    async def test_grep_returns_matching_lines(self, tmp_path):
        """grep returns lines matching regex."""
        grep = make_grep_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        (tmp_path / "a.py").write_text("def foo():\n    pass\n")
        (tmp_path / "b.py").write_text("def bar():\n    return 1\n")
        (tmp_path / "c.txt").write_text("hello world\n")

        result = await grep(r"^def ", str(tmp_path))

        assert "a.py:1:def foo():" in result
        assert "b.py:1:def bar():" in result
        assert "hello" not in result

    @pytest.mark.asyncio
    async def test_grep_with_include_filter(self, tmp_path):
        """grep respects include filter."""
        grep = make_grep_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        (tmp_path / "a.py").write_text("target\n")
        (tmp_path / "b.js").write_text("target\n")

        result = await grep("target", str(tmp_path), include=[".py"])

        assert "a.py" in result
        assert "b.js" not in result

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, tmp_path):
        """grep returns message when no matches."""
        grep = make_grep_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        result = await grep("nomatch12345", str(tmp_path))
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_grep_invalid_pattern(self, tmp_path):
        """grep returns error for invalid regex."""
        grep = make_grep_tool(StorageConfig(allowed_roots=[str(tmp_path)]))
        result = await grep("[invalid", str(tmp_path))
        assert "Invalid regex" in result


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
    async def test_transport_uses_asyncio_to_thread_for_assert_ip_allowed(self):
        """SSRFSafeTransport calls _assert_ip_allowed via asyncio.to_thread."""
        from hestia.tools.builtin.http_get import _assert_ip_allowed

        transport = SSRFSafeTransport()
        request = httpx.Request("GET", "http://example.com/")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # We need the inner transport to not actually make a request
            with patch.object(
                transport._inner, "handle_async_request", new_callable=AsyncMock
            ) as mock_inner:
                mock_inner.return_value = httpx.Response(200, text="ok")
                await transport.handle_async_request(request)

        mock_to_thread.assert_awaited_once()
        assert mock_to_thread.call_args[0][0] == _assert_ip_allowed
        assert mock_to_thread.call_args[0][1] == "example.com"
