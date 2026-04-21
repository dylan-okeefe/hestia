"""Unit tests for CompressedSummaryStrategy."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hestia.context.compressed_summary_strategy import CompressedSummaryStrategy
from hestia.core.types import Message


class FakeCompressor:
    """Fake compressor for testing."""

    def __init__(self, summary: str = "Compressed summary") -> None:
        self.summary = summary
        self.summarize = AsyncMock(return_value=summary)


@pytest.fixture
def compressor():
    return FakeCompressor("Test summary")


@pytest.fixture
def strategy(compressor):
    return CompressedSummaryStrategy(compressor)


class TestHappyPath:
    """Tests for successful compression and insertion."""

    @pytest.mark.asyncio
    async def test_summary_inserted_when_it_fits(self, strategy, compressor):
        """When summary fits in budget, it is inserted after system message."""
        dropped = [Message(role="user", content="old")]
        protected_top = [Message(role="system", content="system")]
        protected_bottom = [Message(role="user", content="new")]
        included = [Message(role="assistant", content="recent")]

        async def count_messages(msgs: list[Message]) -> int:
            return sum(len((m.content or "").split()) for m in msgs)

        result = await strategy.try_splice(
            dropped_history=dropped,
            protected_top=protected_top,
            protected_bottom=protected_bottom,
            included_history=included,
            budget=100,
            count_messages=count_messages,
        )

        assert result is not None
        messages, updated_included, extra_truncated = result
        assert extra_truncated == 0
        assert updated_included == included

        # Summary message should be at index 1 (right after system)
        assert messages[1].role == "system"
        assert "PRIOR CONTEXT SUMMARY" in messages[1].content
        assert "Test summary" in messages[1].content

        compressor.summarize.assert_called_once_with(dropped)

    @pytest.mark.asyncio
    async def test_no_summary_when_compressor_returns_empty(self, compressor):
        """When compressor returns empty string, strategy returns None."""
        compressor.summarize = AsyncMock(return_value="")
        strategy = CompressedSummaryStrategy(compressor)

        result = await strategy.try_splice(
            dropped_history=[Message(role="user", content="old")],
            protected_top=[Message(role="system", content="system")],
            protected_bottom=[Message(role="user", content="new")],
            included_history=[Message(role="assistant", content="recent")],
            budget=100,
            count_messages=AsyncMock(return_value=10),
        )

        assert result is None


class TestRetry:
    """Tests for retry behavior when summary doesn't initially fit."""

    @pytest.mark.asyncio
    async def test_retry_drops_oldest_message(self, strategy, compressor):
        """When summary doesn't fit, oldest included message is dropped."""
        dropped = [Message(role="user", content="old")]
        protected_top = [Message(role="system", content="system")]
        protected_bottom = [Message(role="user", content="new")]
        included = [
            Message(role="assistant", content="oldest included"),
            Message(role="assistant", content="newest included"),
        ]

        call_count = 0

        async def count_messages(msgs: list[Message]) -> int:
            nonlocal call_count
            call_count += 1
            # First call (full list with summary) exceeds budget
            # Second call (without oldest) fits
            total = sum(len((m.content or "").split()) for m in msgs)
            if call_count == 1:
                return total + 1000  # Over budget
            return total  # Under budget

        result = await strategy.try_splice(
            dropped_history=dropped,
            protected_top=protected_top,
            protected_bottom=protected_bottom,
            included_history=included,
            budget=100,
            count_messages=count_messages,
        )

        assert result is not None
        messages, updated_included, extra_truncated = result
        assert extra_truncated == 1
        assert len(updated_included) == 1
        assert updated_included[0].content == "newest included"
        assert "oldest included" not in [m.content for m in messages]

    @pytest.mark.asyncio
    async def test_fallback_when_retry_also_fails(self, strategy, compressor):
        """When summary and retry both exceed budget, returns None."""
        dropped = [Message(role="user", content="old")]
        protected_top = [Message(role="system", content="system")]
        protected_bottom = [Message(role="user", content="new")]
        included = [Message(role="assistant", content="recent")]

        async def count_messages(msgs: list[Message]) -> int:
            return 99999  # Always over budget

        result = await strategy.try_splice(
            dropped_history=dropped,
            protected_top=protected_top,
            protected_bottom=protected_bottom,
            included_history=included,
            budget=100,
            count_messages=count_messages,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_when_no_included_history(self, strategy, compressor):
        """When summary doesn't fit and there's no included history, returns None."""
        dropped = [Message(role="user", content="old")]
        protected_top = [Message(role="system", content="system")]
        protected_bottom = [Message(role="user", content="new")]
        included: list[Message] = []

        async def count_messages(msgs: list[Message]) -> int:
            return 99999  # Always over budget

        result = await strategy.try_splice(
            dropped_history=dropped,
            protected_top=protected_top,
            protected_bottom=protected_bottom,
            included_history=included,
            budget=100,
            count_messages=count_messages,
        )

        assert result is None
