"""Unit tests for HistoryWindowSelector."""

from __future__ import annotations

import pytest

from hestia.context.history_window_selector import HistoryWindowSelector
from hestia.core.types import Message


class MockTokenizer:
    """Mock tokenizer that counts tokens by word count."""

    def __init__(self, overhead: int = 0) -> None:
        self.overhead = overhead

    async def count(self, msg: Message) -> int:
        words = len((msg.content or "").split())
        return words + self.overhead


@pytest.fixture
def selector():
    return HistoryWindowSelector()


@pytest.fixture
def mock_tokenizer():
    return MockTokenizer()


class TestEmptyHistory:
    """Tests for empty history."""

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty(self, selector, mock_tokenizer):
        """Empty history produces empty included and dropped lists."""
        included, dropped, truncated = await selector.select(
            history=[], budget=100, token_counter=mock_tokenizer.count
        )
        assert included == []
        assert dropped == []
        assert truncated == 0


class TestExactBudgetFit:
    """Tests for messages that exactly fit the budget."""

    @pytest.mark.asyncio
    async def test_exact_fit_includes_all(self, selector, mock_tokenizer):
        """When all messages exactly fit budget, nothing is dropped."""
        history = [
            Message(role="user", content="one two"),  # 2 tokens
            Message(role="assistant", content="three four"),  # 2 tokens
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=4, token_counter=mock_tokenizer.count
        )
        assert included == history
        assert dropped == []
        assert truncated == 0

    @pytest.mark.asyncio
    async def test_exact_fit_with_overhead(self, selector):
        """Overhead is included in the token count."""
        tokenizer = MockTokenizer(overhead=1)
        history = [
            Message(role="user", content="one"),  # 1 + 1 = 2 tokens
            Message(role="assistant", content="two"),  # 1 + 1 = 2 tokens
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=4, token_counter=tokenizer.count
        )
        assert included == history
        assert dropped == []
        assert truncated == 0


class TestSingleMessageOverBudget:
    """Tests for a single message that exceeds the budget."""

    @pytest.mark.asyncio
    async def test_single_message_over_budget_is_dropped(self, selector, mock_tokenizer):
        """A message that alone exceeds budget is dropped."""
        history = [
            Message(role="user", content="a b c d e"),  # 5 tokens
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=3, token_counter=mock_tokenizer.count
        )
        assert included == []
        assert dropped == history
        assert truncated == 1


class TestSkipMessage:
    """Tests for skipping a protected message."""

    @pytest.mark.asyncio
    async def test_skip_message_is_not_included(self, selector, mock_tokenizer):
        """The skip_message is excluded from selection."""
        first_user = Message(role="user", content="first")
        history = [
            first_user,
            Message(role="assistant", content="reply"),
        ]
        included, dropped, truncated = await selector.select(
            history=history,
            budget=100,
            token_counter=mock_tokenizer.count,
            skip_message=first_user,
        )
        assert first_user not in included
        assert len(included) == 1
        assert included[0].role == "assistant"


class TestTruncation:
    """Tests for truncation behavior."""

    @pytest.mark.asyncio
    async def test_oldest_messages_dropped_first(self, selector, mock_tokenizer):
        """When budget is tight, oldest messages are dropped."""
        history = [
            Message(role="user", content="old message"),  # 2 tokens
            Message(role="assistant", content="recent reply"),  # 2 tokens
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=2, token_counter=mock_tokenizer.count
        )
        # Newest message is kept
        assert len(included) == 1
        assert included[0].content == "recent reply"
        assert len(dropped) == 1
        assert dropped[0].content == "old message"
        assert truncated == 1

    @pytest.mark.asyncio
    async def test_all_messages_fit_within_budget(self, selector, mock_tokenizer):
        """When budget is large, all messages are included."""
        history = [
            Message(role="user", content="one two three"),
            Message(role="assistant", content="four five six"),
            Message(role="user", content="seven eight nine"),
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=100, token_counter=mock_tokenizer.count
        )
        assert included == history
        assert dropped == []
        assert truncated == 0


class TestToolPairs:
    """Tests for tool call / tool result pair handling."""

    @pytest.mark.asyncio
    async def test_keeps_tool_pair_together(self, selector, mock_tokenizer):
        """Tool call and tool result are kept together when they fit."""
        from hestia.core.types import ToolCall

        assistant_msg = Message(
            role="assistant",
            content="using tool",
            tool_calls=[ToolCall(id="call_1", name="test_tool", arguments={})],
        )
        tool_msg = Message(role="tool", content="result", tool_call_id="call_1")

        history = [
            Message(role="user", content="call tool"),
            assistant_msg,
            tool_msg,
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=100, token_counter=mock_tokenizer.count
        )
        assert assistant_msg in included
        assert tool_msg in included

    @pytest.mark.asyncio
    async def test_drops_tool_pair_together(self, selector, mock_tokenizer):
        """Tool call and tool result are dropped together when they don't fit."""
        from hestia.core.types import ToolCall

        assistant_msg = Message(
            role="assistant",
            content="using tool",
            tool_calls=[ToolCall(id="call_1", name="test_tool", arguments={})],
        )
        tool_msg = Message(role="tool", content="result", tool_call_id="call_1")

        history = [
            Message(role="user", content="call tool"),
            assistant_msg,
            tool_msg,
        ]
        included, dropped, truncated = await selector.select(
            history=history, budget=2, token_counter=mock_tokenizer.count
        )
        assert assistant_msg not in included
        assert tool_msg not in included
        assert assistant_msg in dropped
        assert tool_msg in dropped
        # User message (2 tokens) still fits in budget=2 after pair is dropped
        assert len(included) == 1
        assert included[0].content == "call tool"
        assert truncated == 2

    @pytest.mark.asyncio
    async def test_tool_pair_requires_both_to_fit(self, selector, mock_tokenizer):
        """Tool pair is dropped if the pair together exceeds budget."""
        from hestia.core.types import ToolCall

        assistant_msg = Message(
            role="assistant",
            content="using tool",
            tool_calls=[ToolCall(id="call_1", name="test_tool", arguments={})],
        )
        tool_msg = Message(role="tool", content="result", tool_call_id="call_1")

        history = [
            Message(role="user", content="call tool"),
            assistant_msg,
            tool_msg,
        ]
        # Pair is 2 + 1 = 3 tokens, budget is 1 so nothing fits
        included, dropped, truncated = await selector.select(
            history=history, budget=1, token_counter=mock_tokenizer.count
        )
        assert len(included) == 0
        assert len(dropped) == 3
