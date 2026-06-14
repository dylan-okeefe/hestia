"""Inference client for llama.cpp server."""

import ast
import asyncio
import dataclasses
import json
import logging
import re
import secrets
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from hestia.core.json_repair import repair_json
from hestia.core.serialization import message_to_dict
from hestia.core.types import ChatResponse, Message, StreamDelta, ToolCall, ToolSchema
from hestia.errors import InferenceServerError, InferenceTimeoutError

logger = logging.getLogger(__name__)


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


def _is_valid_url(url: str) -> bool:
    """Reject URLs that contain newlines, XML remnants, or are obviously truncated."""
    if not url or "\n" in url or "</" in url or "<parameter" in url:
        return False
    return url.startswith(("http://", "https://"))


def _parse_json_tool_calls(text: str) -> list[ToolCall]:
    """Format 1: JSON inside <tool_call> tags."""
    tool_calls: list[ToolCall] = []
    for match in re.finditer(r"<tool_call>(.+?)</tool_call>", text, re.DOTALL):
        payload = match.group(1).strip()
        # Some models wrap the JSON in ```json blocks inside the tag
        payload = re.sub(r"^```json\s*|\s*```$", "", payload).strip()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            repaired = repair_json(payload)
            if repaired is None:
                continue
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                continue

        name = data.get("name") or data.get("function", {}).get("name")
        arguments = data.get("arguments") or data.get("function", {}).get("arguments")
        if name and isinstance(arguments, dict):
            tool_calls.append(
                ToolCall(
                    id="tc_xml_" + secrets.token_hex(8),
                    name=name,
                    arguments=arguments,
                )
            )
    return tool_calls


def _parse_adhoc_xml_tool_calls(text: str) -> list[ToolCall]:
    """Format 2: <function=name> <parameter=key> value XML."""
    tool_calls: list[ToolCall] = []
    for block_match in re.finditer(
        r"<tool_call>\s*(.+?)(?:</tool_call>|(?=<tool_call>)|$)", text, re.DOTALL
    ):
        block = block_match.group(1).strip()
        fn_match = re.search(r"<function[=:]\s*([^>\s]+)>", block)
        if not fn_match:
            continue
        name = fn_match.group(1).strip()

        adhoc_args: dict[str, Any] = {}
        # Match <parameter=key>value</parameter> blocks. The value may span
        # multiple lines. Some models close the tag on the next line; others
        # leave it open until the next parameter or the end of the tool_call.
        for param_match in re.finditer(
            r"<parameter[=:]\s*([^>\s]+)>\s*(.+?)(?=<parameter[=:]|</parameter>|</tool_call>|$)",
            block,
            re.DOTALL,
        ):
            key = param_match.group(1).strip()
            val = param_match.group(2).strip()
            # Strip a trailing </parameter> tag if the model included one.
            val = re.sub(r"</parameter>\s*$", "", val).strip()
            # Try to coerce numbers/booleans/dicts, else keep as string.
            # Models often emit Python-like literals (e.g. escaping single quotes
            # as \') that are not valid JSON; fall back to ast.literal_eval which
            # safely handles a superset of JSON literal syntax.
            try:
                val_parsed = json.loads(val.replace("\\'", "'"))
            except json.JSONDecodeError:
                try:
                    val_parsed = ast.literal_eval(val)
                except (SyntaxError, ValueError):
                    val_parsed = val
            adhoc_args[key] = val_parsed

        # --- NSC-ACE-SABER wrapper unwrap ---
        # Some agentic-tuned models emit <function=call_tool> with inner
        # <parameter=name>TOOL_NAME</parameter> and <parameter=arguments>{...}</parameter>.
        # Unwrap to the real tool name and arguments.
        if name == "call_tool" and "name" in adhoc_args and "arguments" in adhoc_args:
            inner_name = adhoc_args["name"]
            inner_args = adhoc_args["arguments"]
            if isinstance(inner_name, str) and isinstance(inner_args, dict):
                name = inner_name
                adhoc_args = inner_args
        # Also handle the case where the model puts a single JSON object
        # inside <parameter=arguments> that contains both name and arguments.
        elif name == "call_tool" and "arguments" in adhoc_args:
            inner = adhoc_args["arguments"]
            if isinstance(inner, dict) and "name" in inner and "arguments" in inner:
                inner_name = inner["name"]
                inner_args = inner["arguments"]
                if isinstance(inner_name, str) and isinstance(inner_args, dict):
                    name = inner_name
                    adhoc_args = inner_args

        # Some models emit a direct tool call like <function=grep>
        # <parameter=arguments>{"path": "...", "pattern": "..."}</parameter>.
        # Unwrap the arguments dict so the parameters land at the top level.
        elif (
            "arguments" in adhoc_args
            and len(adhoc_args) == 1
            and isinstance(adhoc_args["arguments"], dict)
        ):
            adhoc_args = adhoc_args["arguments"]

        # Validate extracted args before creating ToolCall
        if name == "browser_get" and not _is_valid_url(adhoc_args.get("url", "")):
            continue
        if name == "write_file" and (
            not adhoc_args.get("path") or not adhoc_args.get("content")
        ):
            continue

        if name:
            tool_calls.append(
                ToolCall(
                    id="tc_xml_" + secrets.token_hex(8),
                    name=name,
                    arguments=adhoc_args,
                )
            )
    return tool_calls


def _parse_glm_xml_tool_calls(text: str) -> list[ToolCall]:
    """Format 3: GLM-style <arg_key>/<arg_value> XML."""
    tool_calls: list[ToolCall] = []
    for match in re.finditer(r"<tool_call>(.+?)</tool_call>", text, re.DOTALL):
        block = match.group(1).strip()
        lines = block.splitlines()
        if not lines:
            continue
        name = lines[0].strip()
        glm_args: dict[str, Any] = {}
        # Extract <arg_key>/<arg_value> pairs
        keys = re.findall(r"<arg_key>(.+?)</arg_key>", block)
        vals = re.findall(r"<arg_value>(.+?)</arg_value>", block)
        for k, v in zip(keys, vals, strict=False):
            k = k.strip()
            v = v.strip()
            # GLM uses tojson for values, so try JSON parse first
            try:
                v_parsed = json.loads(v)
            except json.JSONDecodeError:
                v_parsed = v
            glm_args[k] = v_parsed

        # Validate extracted args before creating ToolCall
        if name == "browser_get" and not _is_valid_url(glm_args.get("url", "")):
            continue
        if name == "write_file" and (
            not glm_args.get("path") or not glm_args.get("content")
        ):
            continue

        if name and glm_args:
            tool_calls.append(
                ToolCall(
                    id="tc_xml_" + secrets.token_hex(8),
                    name=name,
                    arguments=glm_args,
                )
            )
    return tool_calls


def _parse_bare_json_tool_calls(text: str) -> list[ToolCall]:
    """Format 4: bare JSON objects with name and arguments keys."""
    tool_calls: list[ToolCall] = []
    for match in re.finditer(r"\{\s*[\'\"]?name[\'\"]?\s*:", text):
        start = match.start()
        payload = repair_json(text[start:])
        if payload is None:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue

        name = data.get("name") or data.get("function", {}).get("name")
        arguments = data.get("arguments") or data.get("function", {}).get("arguments")
        if name and isinstance(arguments, dict):
            tool_calls.append(
                ToolCall(
                    id="tc_bare_" + secrets.token_hex(8),
                    name=name,
                    arguments=arguments,
                )
            )
    return tool_calls


def _extract_tool_calls_from_text(text: str) -> list[ToolCall]:
    """Parse XML-style <tool_call> blocks and bare JSON objects from model text/reasoning.

    Qwen3.5 in reasoning mode occasionally emits tool calls inside its
    <think> block (which lands in ``reasoning_content``) but fails to
    output the structured ``tool_calls`` JSON. This fallback extracts
    them so the turn can continue instead of appearing to hang.

    Supports four formats:
    1. JSON object: ``<tool_call>{"name": "...", "arguments": {...}}</tool_call>``
    2. Ad-hoc XML: ``<tool_call>\n<function=name>\n<parameter=key>\nvalue\n...``
    3. GLM XML: ``<tool_call>func_name\n<arg_key>k</arg_key>\n<arg_value>v</arg_value>\n...``
    4. Bare JSON: ``{"name": "...", "arguments": {...}}`` (outside XML tags)
    """
    parsers: list[Callable[[str], list[ToolCall]]] = []
    if "<tool_call>" in text:
        parsers.extend(
            [_parse_json_tool_calls, _parse_adhoc_xml_tool_calls, _parse_glm_xml_tool_calls]
        )
    parsers.append(_parse_bare_json_tool_calls)

    for parser in parsers:
        results = parser(text)
        if results:
            return results
    return []


class InferenceClient:
    """Thin, opinionated wrapper around llama.cpp HTTP server."""

    def __init__(self, base_url: str, model_name: str, timeout: float = 300.0) -> None:
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
        message = choice.get("message") or {}

        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls") or []
        for tc in raw_tool_calls:
            fn = tc.get("function")
            if not fn:
                continue
            name = fn.get("name")
            arguments_raw = fn.get("arguments")
            # Models occasionally emit tool_call arguments as a JSON scalar (string,
            # number, null) instead of an object. ``**arguments`` would then raise
            # TypeError downstream without naming the tool. Validate here.
            try:
                arguments = json.loads(arguments_raw) if arguments_raw is not None else {}
            except json.JSONDecodeError as exc:
                repaired = repair_json(arguments_raw) if arguments_raw is not None else None
                if repaired is not None:
                    logger.info(
                        "Repaired malformed tool_call arguments for %r", name
                    )
                    arguments = json.loads(repaired)
                else:
                    # Gracefully skip malformed tool calls instead of crashing the turn.
                    # Log for debugging; model may retry in next iteration.
                    logger.warning(
                        "Malformed tool_call arguments for %r: %s",
                        name,
                        exc,
                    )
                    continue
            if not isinstance(arguments, dict):
                logger.warning(
                    "tool_call arguments for %r are not a dict: %s",
                    name,
                    type(arguments).__name__,
                )
                continue
            # Unwrap call_tool wrapper: if the model uses call_tool with nested name+arguments,
            # extract the inner tool call directly.
            if name == "call_tool" and "name" in arguments and "arguments" in arguments:
                inner_name = arguments["name"]
                inner_args = arguments["arguments"]
                if isinstance(inner_name, str) and isinstance(inner_args, dict):
                    tool_calls.append(
                        ToolCall(
                            id=tc.get("id") or f"call_{len(tool_calls)}",
                            name=inner_name,
                            arguments=inner_args,
                        )
                    )
                    continue
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or f"call_{len(tool_calls)}",
                    name=name,
                    arguments=arguments,
                )
            )

        if not raw_tool_calls:
            # Fallback: Qwen3.5 in reasoning mode sometimes emits tool calls inside
            # <think> blocks (which land in reasoning_content) but omits the structured
            # tool_calls JSON. Parse XML-style <tool_call> tags as a safety net.
            combined = ""
            reasoning = message.get("reasoning_content")
            if reasoning:
                combined += reasoning + "\n"
            content = message.get("content")
            if content:
                combined += content + "\n"
            if combined:
                fallback = _extract_tool_calls_from_text(combined)
                if fallback:
                    tool_calls = fallback

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
                        # Some servers emit usage in a final chunk with empty choices
                        usage = chunk.get("usage", {})
                        if usage:
                            yield StreamDelta(
                                content="",
                                finish_reason=None,
                                reasoning_content=None,
                                tool_call_chunks=None,
                                prompt_tokens=usage.get("prompt_tokens", 0),
                                completion_tokens=usage.get("completion_tokens", 0),
                                total_tokens=usage.get("total_tokens", 0),
                            )
                        continue
                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")
                    content = delta.get("content", "")
                    usage = chunk.get("usage", {})
                    yield StreamDelta(
                        content=content or "",
                        finish_reason=finish_reason,
                        reasoning_content=delta.get("reasoning_content"),
                        tool_call_chunks=delta.get("tool_calls"),
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
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
