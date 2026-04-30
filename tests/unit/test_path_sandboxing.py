"""Tests for path sandboxing in file system tools."""

import pytest

from hestia.config import StorageConfig
from hestia.tools.builtin.list_dir import make_list_dir_tool


@pytest.mark.asyncio
async def test_list_dir_rejects_outside_root(tmp_path):
    """Test that list_dir rejects paths outside allowed roots."""
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    tool_fn = make_list_dir_tool(StorageConfig(allowed_roots=[str(allowed_root)]))
    result = await tool_fn("/etc")
    assert "Access denied" in result


@pytest.mark.asyncio
async def test_list_dir_allows_inside_root(tmp_path):
    """Test that list_dir allows paths inside allowed roots."""
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    # Create some test files
    (allowed_root / "file1.txt").write_text("hello")
    (allowed_root / "subdir").mkdir()

    tool_fn = make_list_dir_tool(StorageConfig(allowed_roots=[str(allowed_root)]))
    result = await tool_fn(str(allowed_root))

    assert "Access denied" not in result
    assert "file1.txt" in result
    assert "subdir" in result
    assert "[file]" in result
    assert "[dir]" in result


@pytest.mark.asyncio
async def test_list_dir_rejects_relative_escape(tmp_path):
    """Test that list_dir rejects paths that try to escape via .."""
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    # Create a nested directory
    nested = allowed_root / "nested"
    nested.mkdir()

    tool_fn = make_list_dir_tool(StorageConfig(allowed_roots=[str(nested)]))
    # Try to escape using ../
    result = await tool_fn("../")
    assert "Access denied" in result


@pytest.mark.asyncio
async def test_list_dir_handles_nonexistent_directory(tmp_path):
    """Test that list_dir handles non-existent directories gracefully."""
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    tool_fn = make_list_dir_tool(StorageConfig(allowed_roots=[str(allowed_root)]))
    result = await tool_fn(str(allowed_root / "nonexistent"))

    assert "is not a directory" in result


@pytest.mark.asyncio
async def test_list_dir_empty_directory(tmp_path):
    """Test that list_dir handles empty directories."""
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    empty_dir = allowed_root / "empty"
    empty_dir.mkdir()

    tool_fn = make_list_dir_tool(StorageConfig(allowed_roots=[str(allowed_root)]))
    result = await tool_fn(str(empty_dir))

    assert "(empty)" in result
