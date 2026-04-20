"""Unit tests for InferenceClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import Message
from hestia.errors import InferenceServerError


class TestInferenceClient:
    """Tests for the inference client."""

    def test_empty_model_name_raises(self):
        """Creating an InferenceClient with an empty model_name raises ValueError."""
        with pytest.raises(ValueError, match="inference.model_name is required"):
            InferenceClient("http://localhost:8001", "")

    def test_valid_model_name_succeeds(self):
        """Creating an InferenceClient with a valid model_name succeeds."""
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        assert client.base_url == "http://localhost:8001"
        assert client.model_name == "my-model.gguf"


def _make_mock_httpx_response(payload: dict[str, Any]) -> MagicMock:
    """Build a minimal mock httpx Response that mimics .json() + raise_for_status."""
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    mock_response.raise_for_status.return_value = None
    return mock_response


class TestChatEmptyChoicesGuard:
    """T-9 (H-1): empty ``choices`` from llama-server must raise, not IndexError."""

    @pytest.mark.asyncio
    async def test_chat_raises_inference_server_error_on_empty_choices(self) -> None:
        """``{"choices": []}`` surfaces as InferenceServerError with useful message.

        Regression for Copilot H-1: previously the client indexed ``choices[0]``
        unguarded and raised ``IndexError`` with no context, making it very
        hard to tell from logs whether the model was refusing the request,
        the sampler was misconfigured, or a proxy was stripping the response.
        """
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        client._client.post = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_mock_httpx_response({"choices": []})
        )

        with pytest.raises(InferenceServerError, match="returned no choices"):
            await client.chat(messages=[Message(role="user", content="hi")])

        await client.close()

    @pytest.mark.asyncio
    async def test_chat_raises_inference_server_error_on_missing_choices_key(
        self,
    ) -> None:
        """No ``choices`` key at all is treated the same as the empty list."""
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        client._client.post = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_mock_httpx_response({})
        )

        with pytest.raises(InferenceServerError, match="returned no choices"):
            await client.chat(messages=[Message(role="user", content="hi")])

        await client.close()


class TestChatToolCallArgumentsGuard:
    """T-10 (H-2): non-dict tool_call ``arguments`` must raise before ``**args``."""

    @pytest.mark.asyncio
    async def test_chat_raises_when_arguments_is_string_scalar(self) -> None:
        """JSON scalar ``arguments`` → InferenceServerError naming the tool.

        Regression for Copilot H-2: some models emit ``"arguments": "\"hi\""``
        (a JSON-encoded string, not an object). The OpenAI spec requires
        ``arguments`` to be a stringified JSON object; scalar payloads
        would previously slip through and explode downstream as
        ``TypeError: argument of type 'str' is not iterable`` when the
        tool call ran ``**arguments``.
        """
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        client._client.post = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_mock_httpx_response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "function": {
                                            "name": "my_tool",
                                            "arguments": '"a string, not an object"',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                }
            )
        )

        with pytest.raises(
            InferenceServerError,
            match=r"tool_call arguments for 'my_tool' are not a dict: str",
        ):
            await client.chat(messages=[Message(role="user", content="hi")])

        await client.close()

    @pytest.mark.asyncio
    async def test_chat_raises_when_arguments_is_list(self) -> None:
        """JSON array ``arguments`` is also rejected before call dispatch."""
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        client._client.post = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_mock_httpx_response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "function": {
                                            "name": "list_tool",
                                            "arguments": "[1, 2, 3]",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                }
            )
        )

        with pytest.raises(
            InferenceServerError,
            match=r"tool_call arguments for 'list_tool' are not a dict: list",
        ):
            await client.chat(messages=[Message(role="user", content="hi")])

        await client.close()
