"""Unit tests for InferenceClient."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import FunctionSchema, Message, StreamDelta, ToolSchema
from hestia.errors import InferenceBusyError, InferenceServerError, InferenceTimeoutError


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

    @pytest.mark.asyncio
    async def test_reasoning_budget_and_max_tokens_included(
        self, client: InferenceClient, mock_stream_response: Any
    ) -> None:
        """reasoning_budget and max_tokens are forwarded in the request body."""
        mock_stream_response(client, ["data: [DONE]", ""])

        messages = [Message(role="user", content="Hello")]
        async for _delta in client.chat_stream(
            messages, reasoning_budget=1234, max_tokens=567
        ):
            pass

        call_kwargs = client._client.stream.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["json"]["reasoning_budget"] == 1234
        assert call_kwargs["json"]["max_tokens"] == 567


class TestChatRequestBody:
    """Tests for chat() request body construction."""

    @pytest.fixture
    def client(self) -> InferenceClient:
        return InferenceClient("http://localhost:8001", "my-model.gguf")

    @pytest.fixture
    def mock_chat_response(self) -> Any:
        """Return a helper that patches client._request with a canned JSON response."""

        def _apply(client: InferenceClient, data: dict[str, Any]) -> None:
            mock_response = MagicMock()
            mock_response.json.return_value = data
            client._request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        return _apply

    @pytest.mark.asyncio
    async def test_reasoning_budget_and_max_tokens_included(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """reasoning_budget and max_tokens are forwarded in the request body."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {"content": "Hi"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        await client.chat(messages, reasoning_budget=1234, max_tokens=567)

        call_kwargs = client._request.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["json_payload"]["reasoning_budget"] == 1234
        assert call_kwargs["json_payload"]["max_tokens"] == 567


class TestChatMalformedOutput:
    """Tests for chat() malformed-output defense (lines 420-497)."""

    @pytest.fixture
    def client(self) -> InferenceClient:
        return InferenceClient("http://localhost:8001", "my-model.gguf")

    @pytest.fixture
    def mock_chat_response(self) -> Any:
        """Return a helper that patches client._request with a canned JSON response."""

        def _apply(client: InferenceClient, data: dict[str, Any]) -> None:
            mock_response = MagicMock()
            mock_response.json.return_value = data
            client._request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]

        return _apply

    @pytest.mark.asyncio
    async def test_empty_choices_raises_inference_server_error(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """Empty choices list raises InferenceServerError."""
        mock_chat_response(client, {"choices": []})

        messages = [Message(role="user", content="Hello")]
        with pytest.raises(InferenceServerError, match="no choices"):
            await client.chat(messages)

    @pytest.mark.asyncio
    async def test_malformed_json_args_skipped_with_warning(
        self, client: InferenceClient, mock_chat_response: Any, caplog: Any
    ) -> None:
        """Malformed JSON arguments are skipped and a warning is logged."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tc1",
                                    "function": {
                                        "name": "test_tool",
                                        "arguments": "not valid json",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        response = await client.chat(messages)
        assert response.tool_calls == []
        assert any("Malformed tool_call arguments" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_non_dict_args_skipped_with_warning(
        self, client: InferenceClient, mock_chat_response: Any, caplog: Any
    ) -> None:
        """Non-dict arguments are skipped and a warning is logged."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tc1",
                                    "function": {
                                        "name": "test_tool",
                                        "arguments": '"just a string"',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        response = await client.chat(messages)
        assert response.tool_calls == []
        assert any("not a dict" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_call_tool_unwrap_logic(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """call_tool wrapper is unwrapped to the inner tool name and arguments."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tc1",
                                    "function": {
                                        "name": "call_tool",
                                        "arguments": (
                                            '{"name": "inner_tool", '
                                            '"arguments": {"key": "val"}}'
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "inner_tool"
        assert response.tool_calls[0].arguments == {"key": "val"}

    @pytest.mark.asyncio
    async def test_call_tool_unwrap_skipped_when_malformed(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """call_tool with missing inner keys falls back to outer name."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tc1",
                                    "function": {
                                        "name": "call_tool",
                                        "arguments": '{"other": "data"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "call_tool"
        assert response.tool_calls[0].arguments == {"other": "data"}

    @pytest.mark.asyncio
    async def test_xml_fallback_extraction(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """XML <tool_call> tags in content/reasoning are parsed as fallback."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '<tool_call>{"name": "xml_tool", '
                                '"arguments": {"a": 1}}</tool_call>'
                            ),
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "xml_tool"
        assert response.tool_calls[0].arguments == {"a": 1}

    @pytest.mark.asyncio
    async def test_xml_fallback_from_reasoning_content(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """XML <tool_call> tags in reasoning_content are parsed as fallback."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": (
                                '<tool_call>{"name": "reason_tool", '
                                '"arguments": {"b": 2}}</tool_call>'
                            ),
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Hello")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "reason_tool"
        assert response.tool_calls[0].arguments == {"b": 2}

    @pytest.mark.asyncio
    async def test_xml_adhoc_parameter_blocks_with_closing_tags(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """Ad-hoc XML with <parameter=key>value</parameter> blocks parses cleanly."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<tool_call>\n"
                                "<function=write_file>\n"
                                "<parameter=path>\n"
                                "/home/<user>/Documents/Job Search/new_job_listings.md\n"
                                "</parameter>\n"
                                "<parameter=content>\n"
                                "# Job Search Results\n\n"
                                "## Section 1\n"
                                "</parameter>\n"
                                "</function>\n"
                                "</tool_call>"
                            ),
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Write file")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "write_file"
        assert response.tool_calls[0].arguments == {
            "path": "/home/<user>/Documents/Job Search/new_job_listings.md",
            "content": "# Job Search Results\n\n## Section 1",
        }

    @pytest.mark.asyncio
    async def test_xml_adhoc_parameter_blocks_without_closing_tags(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """Ad-hoc XML with open <parameter=key>value blocks still parses."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<tool_call>\n"
                                "<function=write_file>\n"
                                "<parameter=path>\n"
                                "/home/<user>/Documents/Job Search/new_job_listings.md\n"
                                "<parameter=content>\n"
                                "# Job Search Results\n"
                                "</tool_call>"
                            ),
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Write file")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "write_file"
        assert response.tool_calls[0].arguments == {
            "path": "/home/<user>/Documents/Job Search/new_job_listings.md",
            "content": "# Job Search Results",
        }

    @pytest.mark.asyncio
    async def test_xml_adhoc_unwraps_arguments_parameter_for_direct_call(
        self, client: InferenceClient, mock_chat_response: Any
    ) -> None:
        """A direct tool call that wraps args in <parameter=arguments>{...}</parameter> works."""
        mock_chat_response(
            client,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<tool_call>\n"
                                "<function=grep>\n"
                                "<parameter=arguments>\n"
                                '{"path": "/home/<user>/docs", "pattern": "TODO"}\n'
                                "</parameter>\n"
                                "</function>\n"
                                "</tool_call>"
                            ),
                            "tool_calls": [],
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

        messages = [Message(role="user", content="Grep for TODO")]
        response = await client.chat(messages)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "grep"
        assert response.tool_calls[0].arguments == {
            "path": "/home/<user>/docs",
            "pattern": "TODO",
        }


def _chat_payload() -> dict[str, Any]:
    """Minimal valid /v1/chat/completions response body."""
    return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}


class TestServerTypeProfiles:
    """L232 §2: backend profile gating of llama.cpp-only request fields."""

    def _mocked_client(self, client: InferenceClient, body: dict[str, Any]) -> list[httpx.Request]:
        """Attach a MockTransport to the client and record requests."""
        recorded: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded.append(request)
            return httpx.Response(200, json=body)

        client._client = httpx.AsyncClient(  # type: ignore[method-assign]
            transport=httpx.MockTransport(handler)
        )
        return recorded

    def test_defaults_are_llamacpp(self) -> None:
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        assert client.server_type == "llamacpp"
        assert client.supports_tokenize is True
        assert client._semaphore is None

    @pytest.mark.asyncio
    async def test_llamacpp_body_includes_reasoning_budget_and_slot_id(self) -> None:
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        recorded = self._mocked_client(client, _chat_payload())

        await client.chat(
            [Message(role="user", content="hi")], slot_id=2, reasoning_budget=512
        )

        body = json.loads(recorded[0].content)
        assert body["reasoning_budget"] == 512
        assert body["slot_id"] == 2

    @pytest.mark.asyncio
    async def test_openai_compat_body_omits_llamacpp_fields(self) -> None:
        client = InferenceClient(
            "http://127.0.0.1:8080", "qwen3.8", server_type="openai-compat"
        )
        assert client.supports_tokenize is False
        recorded = self._mocked_client(client, _chat_payload())

        await client.chat(
            [Message(role="user", content="hi")], slot_id=2, reasoning_budget=512
        )

        body = json.loads(recorded[0].content)
        assert "reasoning_budget" not in body
        assert "slot_id" not in body
        assert body["model"] == "qwen3.8"

    @pytest.mark.asyncio
    async def test_openai_compat_stream_omits_llamacpp_fields(self) -> None:
        client = InferenceClient(
            "http://127.0.0.1:8080", "qwen3.8", server_type="openai-compat"
        )
        recorded = self._mocked_client(
            client, {"choices": [{"delta": {"content": "hi"}}]}
        )

        async for _delta in client.chat_stream(
            [Message(role="user", content="hi")], slot_id=1, reasoning_budget=256
        ):
            pass

        body = json.loads(recorded[0].content)
        assert body["stream"] is True
        assert "reasoning_budget" not in body
        assert "slot_id" not in body

    @pytest.mark.asyncio
    async def test_health_llamacpp_uses_health_endpoint(self) -> None:
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        recorded = self._mocked_client(client, {"status": "ok"})

        result = await client.health()

        assert recorded[0].url.path == "/health"
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_openai_compat_uses_models_endpoint(self) -> None:
        client = InferenceClient(
            "http://127.0.0.1:8080", "qwen3.8", server_type="openai-compat"
        )
        recorded = self._mocked_client(client, {"data": [{"id": "qwen3.8"}]})

        result = await client.health()

        assert recorded[0].url.path == "/v1/models"
        assert result["data"] == [{"id": "qwen3.8"}]

    @pytest.mark.asyncio
    async def test_health_openai_compat_empty_data_raises(self) -> None:
        client = InferenceClient(
            "http://127.0.0.1:8080", "qwen3.8", server_type="openai-compat"
        )
        self._mocked_client(client, {"data": []})

        with pytest.raises(InferenceServerError, match="no models"):
            await client.health()

    @pytest.mark.asyncio
    async def test_tokenize_openai_compat_raises(self) -> None:
        client = InferenceClient(
            "http://127.0.0.1:8080", "qwen3.8", server_type="openai-compat"
        )

        with pytest.raises(InferenceServerError, match="tokenize unsupported"):
            await client.tokenize("hello")

    @pytest.mark.asyncio
    async def test_tokenize_llamacpp_hits_endpoint(self) -> None:
        client = InferenceClient("http://localhost:8001", "my-model.gguf")
        recorded = self._mocked_client(client, {"tokens": [1, 2, 3]})

        tokens = await client.tokenize("hello")

        assert tokens == [1, 2, 3]
        assert recorded[0].url.path == "/tokenize"


class TestAdmissionControl:
    """L232 §2: client-side admission semaphore for single-slot backends."""

    def _gated_client(
        self,
        handler: Any,
        *,
        queue_timeout: float = 5.0,
    ) -> InferenceClient:
        client = InferenceClient(
            "http://127.0.0.1:8080",
            "qwen3.8",
            server_type="openai-compat",
            max_inflight_requests=1,
            queue_timeout=queue_timeout,
        )
        client._client = httpx.AsyncClient(  # type: ignore[method-assign]
            transport=httpx.MockTransport(handler)
        )
        return client

    @pytest.mark.asyncio
    async def test_second_request_waits_for_first(self) -> None:
        gate = asyncio.Event()
        order: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            order.append("start")
            await gate.wait()
            order.append("end")
            return httpx.Response(200, json=_chat_payload())

        client = self._gated_client(handler)
        messages = [Message(role="user", content="hi")]

        first = asyncio.create_task(client.chat(messages))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(client.chat(messages))
        await asyncio.sleep(0.05)

        # First holds the only permit; second must be queued.
        assert not first.done()
        assert not second.done()
        assert order == ["start"]

        gate.set()
        await asyncio.gather(first, second)
        assert order == ["start", "end", "start", "end"]

    @pytest.mark.asyncio
    async def test_queue_timeout_raises_busy_error(self) -> None:
        gate = asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            await gate.wait()
            return httpx.Response(200, json=_chat_payload())

        client = self._gated_client(handler, queue_timeout=0.05)
        messages = [Message(role="user", content="hi")]

        first = asyncio.create_task(client.chat(messages))
        await asyncio.sleep(0.05)
        with pytest.raises(InferenceBusyError):
            await client.chat(messages)

        gate.set()
        await first  # the admitted request still completes

    @pytest.mark.asyncio
    async def test_semaphore_released_on_http_error(self) -> None:
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json=_chat_payload())

        client = self._gated_client(handler, queue_timeout=0.5)
        messages = [Message(role="user", content="hi")]

        with pytest.raises(InferenceServerError):
            await client.chat(messages)
        # Permit was released despite the error — a follow-up succeeds.
        response = await client.chat(messages)
        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_streaming_goes_through_admission(self) -> None:
        gate = asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            await gate.wait()
            return httpx.Response(
                200,
                content='data: {"choices": [{"delta": {"content": "hi"}}]}\n\ndata: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )

        client = self._gated_client(handler, queue_timeout=0.05)
        messages = [Message(role="user", content="hi")]

        async def consume() -> list[StreamDelta]:
            return [delta async for delta in client.chat_stream(messages)]

        first = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        with pytest.raises(InferenceBusyError):
            await consume()

        gate.set()
        deltas = await first
        assert deltas[0].content == "hi"
