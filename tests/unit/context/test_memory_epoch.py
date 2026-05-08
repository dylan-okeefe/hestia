"""Tests for MemoryEpochBuilder."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.context.memory_epoch import MemoryEpochBuilder
from hestia.core.clock import utcnow
from hestia.memory.store import Memory


class TestMemoryEpochBuilder:
    """Tests for MemoryEpochBuilder."""

    @pytest.mark.asyncio
    async def test_empty_memories_returns_empty_string(self):
        """When no memories exist, build_prefix returns empty string."""
        mock_store = MagicMock()
        mock_store.list_memories = AsyncMock(return_value=[])

        builder = MemoryEpochBuilder(mock_store)
        result = await builder.build_prefix("cli", "user")

        assert result == ""
        mock_store.list_memories.assert_awaited_once_with(
            limit=MemoryEpochBuilder._MAX_MEMORIES,
            platform="cli",
            platform_user="user",
        )

    @pytest.mark.asyncio
    async def test_formatted_block(self):
        """Memories are formatted as a bullet list with tags."""
        mock_store = MagicMock()
        mock_store.list_memories = AsyncMock(
            return_value=[
                Memory(
                    id="m1",
                    content="First memory",
                    tags=["tag1", "tag2"],
                    created_at=utcnow(),
                    session_id="s1",
                    platform="cli",
                    platform_user="user",
                ),
                Memory(
                    id="m2",
                    content="Second memory",
                    tags=[],
                    created_at=utcnow(),
                    session_id="s1",
                    platform="cli",
                    platform_user="user",
                ),
            ]
        )

        builder = MemoryEpochBuilder(mock_store)
        result = await builder.build_prefix("cli", "user")

        assert result.startswith("Relevant memories:")
        assert "- [tag1, tag2] First memory" in result
        assert "- Second memory" in result

    @pytest.mark.asyncio
    async def test_truncation(self):
        """Result is truncated to _MAX_CHARS."""
        mock_store = MagicMock()
        long_content = "x" * MemoryEpochBuilder._MAX_CHARS
        mock_store.list_memories = AsyncMock(
            return_value=[
                Memory(
                    id="m1",
                    content=long_content,
                    tags=[],
                    created_at=utcnow(),
                    session_id="s1",
                    platform="cli",
                    platform_user="user",
                ),
            ]
        )

        builder = MemoryEpochBuilder(mock_store)
        result = await builder.build_prefix("cli", "user")

        assert len(result) <= MemoryEpochBuilder._MAX_CHARS
        assert result.startswith("Relevant memories:")

    @pytest.mark.asyncio
    async def test_graceful_store_failure(self):
        """If the store raises an exception, build_prefix returns empty string."""
        mock_store = MagicMock()
        mock_store.list_memories = AsyncMock(side_effect=RuntimeError("db down"))

        builder = MemoryEpochBuilder(mock_store)
        result = await builder.build_prefix("cli", "user")

        assert result == ""

    @pytest.mark.asyncio
    async def test_old_memories_filtered_out(self):
        """Memories older than _MAX_AGE_DAYS are excluded."""
        mock_store = MagicMock()
        old = utcnow() - timedelta(days=MemoryEpochBuilder._MAX_AGE_DAYS + 1)
        recent = utcnow() - timedelta(days=1)
        mock_store.list_memories = AsyncMock(
            return_value=[
                Memory(
                    id="m1",
                    content="Old memory",
                    tags=[],
                    created_at=old,
                    session_id="s1",
                    platform="cli",
                    platform_user="user",
                ),
                Memory(
                    id="m2",
                    content="Recent memory",
                    tags=[],
                    created_at=recent,
                    session_id="s1",
                    platform="cli",
                    platform_user="user",
                ),
            ]
        )

        builder = MemoryEpochBuilder(mock_store)
        result = await builder.build_prefix("cli", "user")

        assert "Recent memory" in result
        assert "Old memory" not in result

    @pytest.mark.asyncio
    async def test_max_memories_respected(self):
        """Only up to _MAX_MEMORIES are fetched from the store."""
        mock_store = MagicMock()
        mock_store.list_memories = AsyncMock(return_value=[])

        builder = MemoryEpochBuilder(mock_store)
        await builder.build_prefix("cli", "user")

        mock_store.list_memories.assert_awaited_once_with(
            limit=MemoryEpochBuilder._MAX_MEMORIES,
            platform="cli",
            platform_user="user",
        )
