"""Unit tests for built-in tools."""

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.tools.builtin.current_time import current_time
from hestia.tools.builtin.read_artifact import make_read_artifact_tool
from hestia.tools.builtin.read_file import read_file
from hestia.tools.builtin.terminal import terminal


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
    async def test_missing_file(self):
        """Missing file returns error message."""
        result = await read_file("/nonexistent/path/to/file.txt")
        assert "File not found" in result

    @pytest.mark.asyncio
    async def test_directory_not_file(self):
        """Directory returns error message."""
        result = await read_file("/tmp")
        assert "Not a file" in result

    @pytest.mark.asyncio
    async def test_reads_text_file(self, tmp_path):
        """Reads text file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = await read_file(str(test_file))
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_reads_utf8_content(self, tmp_path):
        """Reads UTF-8 content correctly."""
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("Hello 世界 🌍", encoding="utf-8")

        result = await read_file(str(test_file))
        assert "世界" in result
        assert "🌍" in result

    @pytest.mark.asyncio
    async def test_respects_max_bytes(self, tmp_path):
        """Respects max_bytes parameter."""
        test_file = tmp_path / "large.txt"
        test_file.write_text("x" * 10000)

        result = await read_file(str(test_file), max_bytes=100)
        assert len(result) == 100

    @pytest.mark.asyncio
    async def test_binary_file_message(self, tmp_path):
        """Binary files return message, not decoded content."""
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(bytes(range(256)))  # Non-UTF8 bytes

        result = await read_file(str(test_file))
        assert "Binary file" in result


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

    @pytest.mark.asyncio
    async def test_echo_command(self):
        """echo command returns stdout."""
        result = await terminal("echo hello")
        assert "exit_code: 0" in result
        assert "hello" in result
        assert "--- stdout ---" in result

    @pytest.mark.asyncio
    async def test_stderr_captured(self):
        """stderr is captured and returned."""
        result = await terminal("echo error >&2")
        assert "--- stderr ---" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self):
        """Non-zero exit code is reported."""
        result = await terminal("exit 42")
        assert "exit_code: 42" in result

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Timeout is respected."""
        result = await terminal("sleep 5", timeout=0.5)
        assert "TIMEOUT" in result
        assert "0.5s" in result

    @pytest.mark.asyncio
    async def test_list_directory(self):
        """Can list directory contents."""
        result = await terminal("ls /tmp")
        assert "exit_code: 0" in result
        # /tmp should have something in it on most systems
        assert len(result) > len("exit_code: 0\n--- stdout ---\n")
