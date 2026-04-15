"""Inference client for llama.cpp server."""

import json
from typing import Any

import httpx

from hestia.core.types import ChatResponse, Message, ToolCall, ToolSchema
from hestia.errors import InferenceServerError, InferenceTimeoutError


def _strip_historical_reasoning(messages: list[Message]) -> list[Message]:
    """Strip reasoning_content from all messages before sending to API.

    The chat template re-injects think blocks on every request. Stripping
    historical reasoning prevents context explosion.
    """
    result = []
    for msg in messages:
        # Create a new Message without reasoning_content
        new_msg = Message(
            role=msg.role,
            content=msg.content,
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
            reasoning_content=None,  # Strip it
            created_at=msg.created_at,
        )
        result.append(new_msg)
    return result


def _message_to_dict(msg: Message) -> dict[str, Any]:
    """Convert a Message to an OpenAI-compatible dict."""
    result: dict[str, Any] = {
        "role": msg.role,
        "content": msg.content,
    }

    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in msg.tool_calls
        ]

    if msg.tool_call_id:
        result["tool_call_id"] = msg.tool_call_id

    # Note: We intentionally do NOT include reasoning_content here.
    # It gets stripped before sending.

    return result


class InferenceClient:
    """Thin, opinionated wrapper around llama.cpp HTTP server."""

    def __init__(self, base_url: str, model_name: str, timeout: float = 120.0) -> None:
        """Initialize the client.

        Args:
            base_url: Base URL of the llama-server (e.g., http://localhost:8001)
            model_name: Model name to use in requests
            timeout: Default timeout for chat requests (seconds)
        """
        if not model_name:
            raise ValueError(
                "inference.model_name is required — set it to your llama.cpp model filename "
                "(e.g. 'my-model-Q4_K_M.gguf')"
            )
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        # Force HTTP/1.1 — some environments have flaky HTTP/2 negotiation
        self._client = httpx.AsyncClient(http2=False)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        """GET /health. Returns server health info."""
        try:
            response = await self._client.get(
                f"{self.base_url}/health",
                timeout=10.0,
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"Health check timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(f"Health check failed: {e.response.text}") from e

    async def tokenize(self, text: str) -> list[int]:
        """POST /tokenize. Returns token IDs.

        Use len(tokenize(text)) for accurate token counts.
        """
        try:
            response = await self._client.post(
                f"{self.base_url}/tokenize",
                json={"content": text},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            tokens: list[int] = data.get("tokens", [])
            return tokens
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"Tokenize timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(f"Tokenize failed: {e.response.text}") from e

    async def count_request(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> int:
        """Build request body and tokenize for accurate count.

        This builds the exact request body that /v1/chat/completions would see,
        serializes it to JSON, and tokenizes it. This is the way to get
        truthful context budgeting — chars // 4 is wrong.
        """
        # Strip historical reasoning first
        clean_messages = _strip_historical_reasoning(messages)

        # Build the request body
        request_body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [_message_to_dict(m) for m in clean_messages],
        }

        if tools:
            request_body["tools"] = [t.model_dump() for t in tools]

        # Serialize to JSON as it would be sent
        json_text = json.dumps(request_body)
        tokens = await self.tokenize(json_text)
        return len(tokens)

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        slot_id: int | None = None,
        reasoning_budget: int = 2048,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """POST /v1/chat/completions. Returns a ChatResponse.

        Args:
            messages: List of messages (historical reasoning is stripped automatically)
            tools: Optional list of tools to offer
            slot_id: Optional slot ID for slot-targeted inference
            reasoning_budget: Max reasoning tokens (think block)
            max_tokens: Max completion tokens
            temperature: Sampling temperature
        """
        # Strip historical reasoning before building request
        clean_messages = _strip_historical_reasoning(messages)

        request_body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [_message_to_dict(m) for m in clean_messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning_format": "deepseek",
            "reasoning_budget": reasoning_budget,
        }

        if tools:
            request_body["tools"] = [t.model_dump() for t in tools]

        if slot_id is not None:
            request_body["slot_id"] = slot_id

        try:
            response = await self._client.post(
                f"{self.base_url}/v1/chat/completions",
                json=request_body,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"Chat completion timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(f"Chat completion failed: {e.response.text}") from e

        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]

        # Parse tool calls if present
        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls", [])
        if raw_tool_calls:
            for tc in raw_tool_calls:
                fn = tc["function"]
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=fn["name"],
                        arguments=json.loads(fn["arguments"]),
                    )
                )

        # Get usage stats
        usage = data.get("usage", {})

        return ChatResponse(
            content=message.get("content", ""),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "unknown"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    async def slot_save(self, slot_id: int, filename: str) -> None:
        """POST /slots/{id}?action=save"""
        try:
            response = await self._client.post(
                f"{self.base_url}/slots/{slot_id}?action=save",
                json={"filename": filename},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"Slot save timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(f"Slot save failed: {e.response.text}") from e

    async def slot_restore(self, slot_id: int, filename: str) -> None:
        """POST /slots/{id}?action=restore"""
        try:
            response = await self._client.post(
                f"{self.base_url}/slots/{slot_id}?action=restore",
                json={"filename": filename},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"Slot restore timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(f"Slot restore failed: {e.response.text}") from e

    async def slot_erase(self, slot_id: int) -> None:
        """POST /slots/{id}?action=erase"""
        try:
            response = await self._client.post(
                f"{self.base_url}/slots/{slot_id}?action=erase",
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"Slot erase timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(f"Slot erase failed: {e.response.text}") from e
