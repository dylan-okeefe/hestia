"""Inference client for llama.cpp server."""

import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from hestia.core.serialization import message_to_dict
from hestia.core.types import ChatResponse, Message, StreamDelta, ToolCall, ToolSchema
from hestia.errors import InferenceServerError, InferenceTimeoutError


def _strip_historical_reasoning(messages: list[Message]) -> list[Message]:
    """Strip reasoning_content from all messages before sending to API.

    The chat template re-injects think blocks on every request. Stripping
    historical reasoning prevents context explosion.

    Uses a conditional copy: only allocates a new ``Message`` when
    ``reasoning_content`` is actually set, avoiding churn on the
    majority of messages that have no reasoning.
    """
    result: list[Message] = []
    for msg in messages:
        if msg.reasoning_content is not None:
            msg = dataclasses.replace(msg, reasoning_content=None)
        result.append(msg)
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

    async def __aenter__(self) -> "InferenceClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make an HTTP request and translate errors.

        All public HTTP methods should route through here so that error
        handling, retry logic, and request logging live in one place.
        """
        try:
            response = await self._client.request(
                method,
                f"{self.base_url}{path}",
                json=json_payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(f"{method} {path} timed out") from e
        except httpx.HTTPStatusError as e:
            raise InferenceServerError(
                f"{method} {path} returned {e.response.status_code}: {e.response.text}"
            ) from e

    async def health(self) -> dict[str, Any]:
        """GET /health. Returns server health info."""
        response = await self._request("GET", "/health", timeout=10.0)
        result: dict[str, Any] = response.json()
        return result

    async def tokenize(self, text: str) -> list[int]:
        """POST /tokenize. Returns token IDs.

        Use len(tokenize(text)) for accurate token counts.
        """
        response = await self._request(
            "POST",
            "/tokenize",
            json_payload={"content": text},
            timeout=10.0,
        )
        data = response.json()
        tokens: list[int] = data.get("tokens", [])
        return tokens

    async def tokenize_batch(self, texts: list[str]) -> list[int]:
        """Tokenize multiple texts efficiently via the separator approach.

        Joins the texts with a unique separator, makes a single POST /tokenize
        call, then splits the returned token sequence by the separator's token
        signature to recover per-text counts.

        Falls back to individual :meth:`tokenize` calls if the separator
        appears in any text, if the server returns an error, or if the split
        does not yield the expected number of segments.

        Args:
            texts: List of texts to tokenize.

        Returns:
            List of token counts, one per input text.
        """
        if not texts:
            return []
        if len(texts) == 1:
            tokens = await self.tokenize(texts[0])
            return [len(tokens)]

        separator = "\x00\x00BATCH_SEPARATOR\x00\x00"

        if any(separator in t for t in texts):
            results = await asyncio.gather(*(self.tokenize(t) for t in texts))
            return [len(r) for r in results]

        try:
            sep_tokens = await self.tokenize(separator)
            joined = separator.join(texts)
            all_tokens = await self.tokenize(joined)
        except (InferenceServerError, InferenceTimeoutError):
            results = await asyncio.gather(*(self.tokenize(t) for t in texts))
            return [len(r) for r in results]

        if not sep_tokens:
            results = await asyncio.gather(*(self.tokenize(t) for t in texts))
            return [len(r) for r in results]

        counts: list[int] = []
        start = 0
        sep_len = len(sep_tokens)
        i = 0

        while i <= len(all_tokens) - sep_len:
            if all_tokens[i : i + sep_len] == sep_tokens:
                counts.append(i - start)
                start = i + sep_len
                i = start
            else:
                i += 1

        counts.append(len(all_tokens) - start)

        if len(counts) != len(texts):
            results = await asyncio.gather(*(self.tokenize(t) for t in texts))
            return [len(r) for r in results]

        return counts

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
            "messages": [message_to_dict(m) for m in clean_messages],
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
            "messages": [message_to_dict(m) for m in clean_messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning_format": "deepseek",
            "reasoning_budget": reasoning_budget,
        }

        if tools:
            request_body["tools"] = [t.model_dump() for t in tools]

        if slot_id is not None:
            request_body["slot_id"] = slot_id

        response = await self._request(
            "POST",
            "/v1/chat/completions",
            json_payload=request_body,
            timeout=self.timeout,
        )

        data = response.json()
        # Guard the empty-choices case: llama-server (and OpenAI-compatible proxies)
        # can return ``{"choices": []}`` on certain sampler configurations or when the
        # request is refused by a safety layer; indexing [0] unguarded raises IndexError
        # with no useful provenance.
        choices = data.get("choices", [])
        if not choices:
            raise InferenceServerError("inference returned no choices")
        choice = choices[0]
        message = choice["message"]

        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls", [])
        if raw_tool_calls:
            for tc in raw_tool_calls:
                fn = tc["function"]
                # Models occasionally emit tool_call arguments as a JSON scalar (string,
                # number, null) instead of an object. ``**arguments`` would then raise
                # TypeError downstream without naming the tool. Validate here.
                try:
                    arguments = json.loads(fn["arguments"])
                except json.JSONDecodeError as exc:
                    raise InferenceServerError(
                        f"tool_call arguments for {fn['name']!r} are malformed JSON: {exc}"
                    ) from exc
                if not isinstance(arguments, dict):
                    raise InferenceServerError(
                        f"tool_call arguments for {fn['name']!r} are not a dict: "
                        f"{type(arguments).__name__}"
                    )
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=fn["name"],
                        arguments=arguments,
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

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        slot_id: int | None = None,
        reasoning_budget: int = 2048,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamDelta]:
        """POST /v1/chat/completions with streaming. Yields StreamDelta chunks.

        Args:
            messages: List of messages (historical reasoning is stripped automatically)
            tools: Optional list of tools to offer
            slot_id: Optional slot ID for slot-targeted inference
            reasoning_budget: Max reasoning tokens (think block)
            max_tokens: Max completion tokens
            temperature: Sampling temperature
        """
        clean_messages = _strip_historical_reasoning(messages)

        request_body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [message_to_dict(m) for m in clean_messages],
            "stream": True,
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
            async with self._client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=request_body,
                timeout=self.timeout,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    await e.response.aread()
                    raise InferenceServerError(
                        f"POST /v1/chat/completions returned {e.response.status_code}: "
                        f"{e.response.text}"
                    ) from e

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")
                    content = delta.get("content", "")
                    yield StreamDelta(
                        content=content or "",
                        finish_reason=finish_reason,
                    )
        except httpx.TimeoutException as e:
            raise InferenceTimeoutError(
                "POST /v1/chat/completions timed out"
            ) from e

    async def slot_save(self, slot_id: int, filename: str) -> None:
        """POST /slots/{id}?action=save"""
        await self._request(
            "POST",
            f"/slots/{slot_id}?action=save",
            json_payload={"filename": filename},
            timeout=30.0,
        )

    async def slot_restore(self, slot_id: int, filename: str) -> None:
        """POST /slots/{id}?action=restore"""
        await self._request(
            "POST",
            f"/slots/{slot_id}?action=restore",
            json_payload={"filename": filename},
            timeout=30.0,
        )

    async def slot_erase(self, slot_id: int) -> None:
        """POST /slots/{id}?action=erase"""
        await self._request(
            "POST",
            f"/slots/{slot_id}?action=erase",
            timeout=10.0,
        )
