"""Unit tests for InferenceClient."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import FunctionSchema, Message, StreamDelta, ToolSchema
from hestia.errors import InferenceServerError, InferenceTimeoutError


class TestInferenceClient:
    """Tests for the inference client."""

    def test_empty_model_name_raises(self) -> None:
        """Creating an InferenceClient with an empty model_name raises ValueError."""
        with pytest.raises(ValueError, match="inference.model_name is required"):
            InferenceClient("http://localhost:8001", "")

    def test_valid_model_name_succeeds(self) -> None:
        """Creating an InferenceClient with a valid model_name succeeds."""
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        assert client.base_url == "http://localhost:8001"
        assert client.model_name == "my-model.gguf"


class TestChatStream:
    """Tests for the chat_stream method."""

    @pytest.fixture
    def client(self) -> InferenceClient:
        return InferenceClient("http://localhost:8001", "my-model.gguf")

    @pytest.fixture
    def mock_stream_response(self) -> Any:
        """Return a helper that patches client._client.stream with mocked SSE lines."""

        def _apply(client: InferenceClient, lines: list[str]) -> None:
            async def _aiter_lines() -> Any:
                for line in lines:
                    yield line

            mock_response = MagicMock()
            mock_response.aiter_lines = _aiter_lines
            mock_response.raise_for_status = MagicMock()

            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            client._client.stream = MagicMock(return_value=mock_stream)  # type: ignore[method-assign]

        return _apply

    @pytest.mark.asyncio
    async def test_yields_stream_deltas(
        self, client: InferenceClient, mock_stream_response: Any
    ) -> None:
        """chat_stream yields StreamDelta objects for each content chunk."""
        mock_stream_response(
            client,
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                "",
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                "",
                "data: [DONE]",
                "",
            ],
        )

        messages = [Message(role="user", content="Say hello")]
        deltas = []
        async for delta in client.chat_stream(messages):
            deltas.append(delta)

        assert len(deltas) == 2
        assert deltas[0] == StreamDelta(content="Hello")
        assert deltas[1] == StreamDelta(content=" world")

        # Verify stream=True was sent
        call_kwargs = client._client.stream.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["json"]["stream"] is True

    @pytest.mark.asyncio
    async def test_finish_reason_passed_through(
        self, client: InferenceClient, mock_stream_response: Any
    ) -> None:
        """Finish reason from the last chunk is included in the StreamDelta."""
        mock_stream_response(
            client,
            [
                'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}',
                "",
                "data: [DONE]",
                "",
            ],
        )

        messages = [Message(role="user", content="Hi")]
        deltas = []
        async for delta in client.chat_stream(messages):
            deltas.append(delta)

        assert len(deltas) == 1
        assert deltas[0] == StreamDelta(content="", finish_reason="stop")

    @pytest.mark.asyncio
    async def test_skips_malformed_json(
        self, client: InferenceClient, mock_stream_response: Any
    ) -> None:
        """Malformed JSON lines are skipped without crashing."""
        mock_stream_response(
            client,
            [
                "data: not-json",
                "",
                'data: {"choices":[{"delta":{"content":"ok"}}]}',
                "",
                "data: [DONE]",
                "",
            ],
        )

        messages = [Message(role="user", content="Test")]
        deltas = []
        async for delta in client.chat_stream(messages):
            deltas.append(delta)

        assert len(deltas) == 1
        assert deltas[0].content == "ok"

    @pytest.mark.asyncio
    async def test_skips_empty_choices(
        self, client: InferenceClient, mock_stream_response: Any
    ) -> None:
        """Chunks with empty choices are skipped."""
        mock_stream_response(
            client,
            [
                'data: {"choices":[]}',
                "",
                'data: {"choices":[{"delta":{"content":"yes"}}]}',
                "",
                "data: [DONE]",
                "",
            ],
        )

        messages = [Message(role="user", content="Test")]
        deltas = []
        async for delta in client.chat_stream(messages):
            deltas.append(delta)

        assert len(deltas) == 1
        assert deltas[0].content == "yes"

    @pytest.mark.asyncio
    async def test_http_status_error_translated(self, client: InferenceClient) -> None:
        """HTTP status errors are translated to InferenceServerError."""
        request = httpx.Request("POST", "http://localhost:8001/v1/chat/completions")
        error_response = httpx.Response(500, text="Internal Server Error", request=request)

        def _raise() -> None:
            raise httpx.HTTPStatusError(
                "Server error", request=request, response=error_response
            )

        mock_response = MagicMock()
        mock_response.raise_for_status = _raise

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        client._client.stream = MagicMock(return_value=mock_stream)  # type: ignore[method-assign]

        messages = [Message(role="user", content="Test")]
        with pytest.raises(InferenceServerError, match="500"):
            async for _delta in client.chat_stream(messages):
                pass  # pragma: no cover

    @pytest.mark.asyncio
    async def test_timeout_error_translated(self, client: InferenceClient) -> None:
        """Timeout errors are translated to InferenceTimeoutError."""
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        client._client.stream = MagicMock(return_value=mock_stream)  # type: ignore[method-assign]

        messages = [Message(role="user", content="Test")]
        with pytest.raises(InferenceTimeoutError, match="timed out"):
            async for _delta in client.chat_stream(messages):
                pass  # pragma: no cover

    @pytest.mark.asyncio
    async def test_tools_and_slot_id_included(
        self, client: InferenceClient, mock_stream_response: Any
    ) -> None:
        """tools and slot_id are forwarded in the request body."""
        mock_stream_response(client, ["data: [DONE]", ""])

        tool = ToolSchema(
            function=FunctionSchema(
                name="test_tool",
                description="A test tool",
                parameters={"type": "object", "properties": {}},
            )
        )

        messages = [Message(role="user", content="Use tool")]
        async for _delta in client.chat_stream(messages, tools=[tool], slot_id=3):
            pass

        call_kwargs = client._client.stream.call_args.kwargs  # type: ignore[attr-defined]
        assert "tools" in call_kwargs["json"]
        assert call_kwargs["json"]["slot_id"] == 3
