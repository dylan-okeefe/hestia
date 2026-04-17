"""Unit tests for HistoryCompressor implementations."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.context.compressor import InferenceHistoryCompressor
from hestia.core.types import ChatResponse, Message


class TestInferenceHistoryCompressor:
    """Tests for the default inference-based compressor."""

    @pytest.mark.asyncio
    async def test_empty_dropped_returns_empty(self):
        """Empty dropped list returns empty string without calling inference."""
        inference = MagicMock()
        inference.chat = AsyncMock()

        compressor = InferenceHistoryCompressor(inference)
        result = await compressor.summarize([])

        assert result == ""
        inference.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path(self):
        """Compressor calls inference and returns trimmed summary."""
        inference = MagicMock()
        inference.chat = AsyncMock(
            return_value=ChatResponse(
                content="User asked about Python and decided to use Flask.",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )
        )

        compressor = InferenceHistoryCompressor(inference, max_chars=400)
        dropped = [
            Message(role="user", content="What framework?"),
            Message(role="assistant", content="Flask is light."),
        ]

        result = await compressor.summarize(dropped)

        assert result == "User asked about Python and decided to use Flask."
        inference.chat.assert_called_once()
        call_kwargs = inference.chat.call_args.kwargs
        assert call_kwargs["slot_id"] is None
        assert call_kwargs["reasoning_budget"] == 0

    @pytest.mark.asyncio
    async def test_inference_error_fallback(self):
        """If inference raises, return empty string."""
        inference = MagicMock()
        inference.chat = AsyncMock(side_effect=RuntimeError("server down"))

        compressor = InferenceHistoryCompressor(inference)
        dropped = [Message(role="user", content="Hello")]

        result = await compressor.summarize(dropped)
        assert result == ""

    @pytest.mark.asyncio
    async def test_oversize_truncation(self):
        """Summaries longer than max_chars are truncated."""
        long_text = "A" * 500
        inference = MagicMock()
        inference.chat = AsyncMock(
            return_value=ChatResponse(
                content=long_text,
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )
        )

        compressor = InferenceHistoryCompressor(inference, max_chars=100)
        dropped = [Message(role="user", content="Hello")]

        result = await compressor.summarize(dropped)
        assert len(result) == 100
