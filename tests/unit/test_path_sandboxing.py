"""Unit tests for path sandboxing in file tools."""

import pytest

from hestia.tools.builtin.path_utils import check_path_allowed
from hestia.tools.builtin.read_file import make_read_file_tool
from hestia.tools.builtin.write_file import make_write_file_tool


class TestCheckPathAllowed:
    """Tests for the check_path_allowed helper."""

    def test_path_inside_root_allowed(self, tmp_path):
        """Paths inside allowed root are allowed."""
        root = str(tmp_path)
        test_file = str(tmp_path / "test.txt")
        result = check_path_allowed(test_file, [root])
        assert result is None

    def test_path_outside_root_denied(self, tmp_path):
        """Paths outside allowed root are denied."""
        root = str(tmp_path)
        result = check_path_allowed("/etc/passwd", [root])
        assert result is not None
        assert "Access denied" in result
        assert "/etc/passwd" in result

    def test_nested_path_allowed(self, tmp_path):
        """Nested paths inside allowed root are allowed."""
        root = str(tmp_path)
        nested = tmp_path / "subdir" / "deep" / "file.txt"
        result = check_path_allowed(str(nested), [root])
        assert result is None

    def test_relative_path_resolved(self, tmp_path):
        """Relative paths are resolved against allowed root."""
        root = str(tmp_path)
        # Create a subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result = check_path_allowed(str(subdir / ".." / "test.txt"), [root])
        # This should resolve to tmp_path/test.txt which is allowed
        assert result is None

    def test_traversal_attack_blocked(self, tmp_path):
        """Path traversal attacks are blocked."""
        root = str(tmp_path / "allowed")
        # Try to escape via ..
        result = check_path_allowed(str(tmp_path / "allowed" / ".." / ".." / "etc" / "passwd"), [root])
        assert result is not None
        assert "Access denied" in result

    def test_multiple_roots_tries_all(self, tmp_path):
        """If path is in any allowed root, it's allowed."""
        root1 = str(tmp_path / "dir1")
        root2 = str(tmp_path / "dir2")
        # Create both directories
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir2").mkdir()

        # Path in root2 should be allowed even if not in root1
        test_file = str(tmp_path / "dir2" / "file.txt")
        result = check_path_allowed(test_file, [root1, root2])
        assert result is None


class TestReadFileSandboxing:
    """Tests for read_file path sandboxing."""

    @pytest.mark.asyncio
    async def test_read_inside_root_succeeds(self, tmp_path):
        """Reading a file inside allowed root succeeds."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        tool = make_read_file_tool([str(tmp_path)])
        result = await tool(str(test_file))
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_outside_root_blocked(self, tmp_path):
        """Reading a file outside allowed root is blocked."""
        tool = make_read_file_tool([str(tmp_path)])
        result = await tool("/etc/passwd")
        assert "Access denied" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_inside_root(self, tmp_path):
        """Reading nonexistent file inside root returns file not found."""
        tool = make_read_file_tool([str(tmp_path)])
        result = await tool(str(tmp_path / "nonexistent.txt"))
        assert "File not found" in result


class TestWriteFileSandboxing:
    """Tests for write_file path sandboxing."""

    @pytest.mark.asyncio
    async def test_write_inside_root_succeeds(self, tmp_path):
        """Writing a file inside allowed root succeeds."""
        tool = make_write_file_tool([str(tmp_path)])
        test_file = tmp_path / "output.txt"
        result = await tool(str(test_file), "Hello, World!")
        assert "Wrote" in result
        assert test_file.read_text() == "Hello, World!"

    @pytest.mark.asyncio
    async def test_write_outside_root_blocked(self, tmp_path):
        """Writing a file outside allowed root is blocked."""
        tool = make_write_file_tool([str(tmp_path)])
        result = await tool("/etc/passwd", "malicious")
        assert "Access denied" in result
        # Verify file was NOT written
        import os
        assert not os.path.exists("/etc/passwd") or open("/etc/passwd").read() != "malicious"

    @pytest.mark.asyncio
    async def test_create_nested_directories_inside_root(self, tmp_path):
        """Creating nested directories inside root succeeds."""
        tool = make_write_file_tool([str(tmp_path)])
        nested = tmp_path / "deep" / "nested" / "file.txt"
        result = await tool(str(nested), "content")
        assert "Wrote" in result
        assert nested.read_text() == "content"

    @pytest.mark.asyncio
    async def test_traversal_write_blocked(self, tmp_path):
        """Path traversal in write is blocked."""
        allowed_root = tmp_path / "allowed"
        allowed_root.mkdir()

        # Create a file outside the allowed root
        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("original")

        tool = make_write_file_tool([str(allowed_root)])
        # Try to escape via ..
        result = await tool(str(allowed_root / ".." / "outside.txt"), "hacked")
        assert "Access denied" in result
        # Verify original content preserved
        assert outside_file.read_text() == "original"
