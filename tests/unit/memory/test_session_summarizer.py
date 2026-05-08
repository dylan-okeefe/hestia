"""Unit tests for SessionSummarizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import ChatResponse, Message
from hestia.memory.session_summarizer import SessionSummarizer


class TestSessionSummarizer:
    @pytest.fixture
    def summarizer(self):
        inference = MagicMock()
        return SessionSummarizer(inference=inference)

    @pytest.mark.asyncio
    async def test_empty_messages_returns_empty(self, summarizer):
        assert await summarizer.summarize([]) == ""

    @pytest.mark.asyncio
    async def test_single_message_returns_empty(self, summarizer):
        messages = [Message(role="user", content="Hello")]
        assert await summarizer.summarize(messages) == ""

    @pytest.mark.asyncio
    async def test_mock_inference(self, summarizer):
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
            Message(role="user", content="What's the weather?"),
            Message(role="assistant", content="It's sunny"),
        ]

        summarizer._inference.chat = AsyncMock(
            return_value=ChatResponse(
                content="User asked about weather. It is sunny.",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )
        )

        result = await summarizer.summarize(messages)
        assert result == "User asked about weather. It is sunny."
        summarizer._inference.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_inference_returns_empty(self, summarizer):
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
        ]

        summarizer._inference.chat = AsyncMock(side_effect=Exception("Inference error"))

        result = await summarizer.summarize(messages)
        assert result == ""

    @pytest.mark.asyncio
    async def test_filters_non_dialogue_roles(self, summarizer):
        """system and tool messages are excluded from the summary prompt."""
        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="tool", content="tool result"),
        ]

        summarizer._inference.chat = AsyncMock(
            return_value=ChatResponse(
                content="Summary",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=5,
                completion_tokens=2,
                total_tokens=7,
            )
        )

        await summarizer.summarize(messages)
        call_args = summarizer._inference.chat.call_args[1]["messages"]
        roles = [m.role for m in call_args]
        assert "system" in roles  # The prompt itself
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" not in roles
        assert roles.count("system") == 1  # Only the summary prompt

    @pytest.mark.asyncio
    async def test_empty_content_skipped(self, summarizer):
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content=""),
            Message(role="user", content=""),
            Message(role="assistant", content="Hi"),
        ]

        summarizer._inference.chat = AsyncMock(
            return_value=ChatResponse(
                content="Summary",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=5,
                completion_tokens=2,
                total_tokens=7,
            )
        )

        await summarizer.summarize(messages)
        call_args = summarizer._inference.chat.call_args[1]["messages"]
        contents = [m.content for m in call_args if m.role != "system"]
        assert contents == ["Hello", "Hi"]
