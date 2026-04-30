"""ContextBuilder assembles the message list for a turn under a token budget."""

import asyncio
import json
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from hestia.context.compressed_summary_strategy import CompressedSummaryStrategy
from hestia.context.compressor import HistoryCompressor
from hestia.context.history_window_selector import HistoryWindowSelector
from hestia.core.inference import InferenceClient
from hestia.core.serialization import message_to_dict
from hestia.core.types import Message, Session, ToolSchema
from hestia.errors import ContextTooLargeError
from hestia.policy.engine import PolicyEngine


@dataclass(frozen=True)
class _PrefixLayer:
    name: str
    value: str | None


@dataclass
class BuildResult:
    """Result of building context for a turn."""

    messages: list[Message]
    tokens_used: int
    tokens_budget: int
    truncated_count: int  # how many historical messages got dropped
    kept_first_user: bool  # sanity flag for the Qwen template requirement
    memory_epoch_included: bool  # whether memory epoch was included


@lru_cache(maxsize=8)
def _load_calibration(path: Path) -> dict[str, Any]:
    """Load calibration data from disk (cached by path)."""
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
        return data


class ContextBuilder:
    """Assembles the message list for a turn under a token budget.

    Uses a two-number calibration formula:
        corrected = int(predicted_body / body_factor) + meta_tool_overhead

    Where:
    - predicted_body: count_request(messages, tools=[]) - body only
    - body_factor: ratio of predicted/actual for tool-free requests
    - meta_tool_overhead: constant tokens added when tools are present

    This split is necessary because the client-side JSON tokenization differs
    from the server's chat-template expansion for tool schemas.

    Key design principles:
    - Always include the system prompt
    - Always include the first user message (Qwen template requirement)
    - Always include the new user message
    - Include as much recent history as fits in budget
    - Drop oldest non-protected messages if we overflow
    - Never split a tool_call / tool_result pair
    """

    def __init__(
        self,
        inference_client: InferenceClient,
        policy: PolicyEngine,
        body_factor: float = 1.0,
        meta_tool_overhead: int = 0,
        identity_prefix: str | None = None,
        memory_epoch_prefix: str | None = None,
        style_prefix: str | None = None,
        compressor: HistoryCompressor | None = None,
        compress_on_overflow: bool = False,
    ):
        """Initialize with inference client and policy.

        Args:
            inference_client: Client for token counting
            policy: Policy engine for budget decisions
            body_factor: Correction factor for message body tokenization
            meta_tool_overhead: Constant overhead when tools are present
            identity_prefix: Optional compiled identity view to prepend to system prompt
            memory_epoch_prefix: Optional compiled memory epoch to prepend to system prompt
            style_prefix: Optional style profile addendum to prepend to system prompt
            compressor: Optional history compressor for overflow recovery
            compress_on_overflow: Whether to compress dropped history
        """
        self._inference = inference_client
        self._policy = policy
        self._body_factor = body_factor
        self._meta_tool_overhead = meta_tool_overhead
        self._identity_prefix = identity_prefix
        self._memory_epoch_prefix = memory_epoch_prefix
        self._style_prefix = style_prefix
        self._compressor = compressor
        self._compress_on_overflow = compress_on_overflow
        self._tokenize_cache: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._join_overhead: int | None = None
        self._system_token_count: int | None = None
        self._last_system_cache_key: int | None = None

    def set_identity_prefix(self, identity_prefix: str | None) -> None:
        """Set the identity prefix to prepend to system prompts.

        Args:
            identity_prefix: Compiled identity view, or None to clear
        """
        self._identity_prefix = identity_prefix

    def set_memory_epoch_prefix(self, memory_epoch_prefix: str | None) -> None:
        """Set the memory epoch prefix to prepend to system prompts.

        Args:
            memory_epoch_prefix: Compiled memory epoch, or None to clear
        """
        self._memory_epoch_prefix = memory_epoch_prefix

    def set_style_prefix(self, style_prefix: str | None) -> None:
        """Set the style profile prefix to prepend to system prompts.

        Args:
            style_prefix: Style profile text, or None to clear
        """
        self._style_prefix = style_prefix

    def enable_compression(self, compressor: HistoryCompressor) -> None:
        """Attach a history compressor and turn on overflow compression.

        Called by the CLI wiring when ``CompressionConfig.enabled`` is true,
        so builders constructed via :meth:`from_calibration_file` can still
        opt in to compression without reconstructing.
        """
        self._compressor = compressor
        self._compress_on_overflow = True

    @classmethod
    def from_calibration_file(
        cls,
        inference_client: InferenceClient,
        policy: PolicyEngine,
        calibration_path: Path | None = None,
    ) -> "ContextBuilder":
        """Create a ContextBuilder with calibration from file.

        Args:
            inference_client: Client for token counting
            policy: Policy engine
            calibration_path: Path to calibration.json. Defaults to docs/calibration.json

        Returns:
            ContextBuilder with loaded calibration values
        """
        path = calibration_path or Path("docs/calibration.json")
        if path.exists():
            data = _load_calibration(path)
            body_factor = data.get("body_factor", 1.0)
            meta_tool_overhead = data.get("meta_tool_overhead_tokens", 0)
        else:
            body_factor = 1.0
            meta_tool_overhead = 0

        return cls(inference_client, policy, body_factor, meta_tool_overhead)

    async def warm_up(self) -> None:
        """Eagerly compute join overhead so the first turn isn't slowed down."""
        if self._join_overhead is not None:
            return
        dummy_history = [
            Message(role="user", content="warmup"),
            Message(role="assistant", content="warmup"),
        ]
        overhead = await self._compute_join_overhead(dummy_history, [], [])
        self._join_overhead = overhead

    def _prefix_layers(self) -> list[_PrefixLayer]:
        """Return prefix layers in canonical assembly order."""
        return [
            _PrefixLayer("identity", self._identity_prefix),
            _PrefixLayer("memory_epoch", self._memory_epoch_prefix),
            _PrefixLayer("style", self._style_prefix),
        ]

    async def _compute_join_overhead(
        self,
        history: list[Message],
        protected_top: list[Message],
        protected_bottom: list[Message],
    ) -> int:
        """Compute the per-message JSON framing overhead in tokens.

        Measures the incremental token cost of adding a second message to a
        single-message request body. This is a function of the request JSON
        shape, not message content, so it is constant across the lifetime
        of an InferenceClient/model pair.

        Callers swapping models on the same ContextBuilder instance will see
        stale overhead — but the codebase never does that today.
        """
        _m1: Message | None = None
        _m2: Message | None = None
        if len(history) >= 2:
            _m1, _m2 = history[0], history[1]
        elif len(protected_top + protected_bottom) >= 2:
            _combo = protected_top + protected_bottom
            _m1, _m2 = _combo[0], _combo[1]
        if _m1 is not None and _m2 is not None:
            _single_body = json.dumps(
                {"model": self._inference.model_name, "messages": [message_to_dict(_m1)]}
            )
            _combined_body = json.dumps(
                {
                    "model": self._inference.model_name,
                    "messages": [message_to_dict(_m1), message_to_dict(_m2)],
                }
            )
            _single_count = len(await self._inference.tokenize(_single_body))
            _combined_count = len(await self._inference.tokenize(_combined_body))
            return (
                _combined_count - _single_count - await self._count_tokens(_m2)
            )
        return 0

    async def build(
        self,
        session: Session,
        history: list[Message],
        system_prompt: str,
        tools: list[ToolSchema],
        new_user_message: Message | None = None,
    ) -> BuildResult:
        """Assemble messages for a turn under token budget."""
        raw_budget = self._policy.turn_token_budget(session)
        truncated_count = 0

        parts = [layer.value for layer in self._prefix_layers() if layer.value]
        parts.append(system_prompt)
        effective_prompt = "\n\n".join(parts)
        memory_epoch_included = self._memory_epoch_prefix is not None
        system_msg = Message(role="system", content=effective_prompt)

        first_user_msg: Message | None = None
        for msg in history:
            if msg.role == "user":
                first_user_msg = msg
                break

        protected_top: list[Message] = [system_msg]
        if first_user_msg:
            protected_top.append(first_user_msg)
        protected_bottom: list[Message] = [new_user_message] if new_user_message else []

        protected_body = await self._count_body(protected_top + protected_bottom)
        protected_count = self._apply_correction(protected_body, has_tools=len(tools) > 0)

        if protected_count > raw_budget:
            raise ContextTooLargeError(
                f"Protected context ({protected_count} tokens) exceeds per-slot budget "
                f"({raw_budget}). Reduce identity, memory_epoch, or run /reset."
            )

        if self._join_overhead is None:
            overhead = await self._compute_join_overhead(
                history, protected_top, protected_bottom
            )
            # Only cache when we had enough messages to measure, or when the
            # overhead is non-zero (indicating a real measurement).
            if overhead != 0 or len(history) >= 2 or len(protected_top + protected_bottom) >= 2:
                self._join_overhead = overhead
        _join_overhead = self._join_overhead or 0

        available_budget = raw_budget - protected_count

        # Batch token counting: compute all history message counts in parallel
        history_counts: dict[int, int] = {}
        if history:
            counts = await asyncio.gather(*(self._count_tokens(msg) for msg in history))
            history_counts = {
                id(msg): c + _join_overhead
                for msg, c in zip(history, counts, strict=True)
            }

        async def _history_token_count(msg: Message) -> int:
            return history_counts.get(id(msg), 0)

        selector = HistoryWindowSelector()
        included, dropped, truncated_count = await selector.select(
            history=history, budget=available_budget, token_counter=_history_token_count,
            skip_message=first_user_msg,
        )

        final_messages = list(protected_top)
        final_messages.extend(included)
        final_messages.extend(protected_bottom)

        if self._compressor is not None and self._compress_on_overflow and dropped:
            strategy = CompressedSummaryStrategy(self._compressor)
            result = await strategy.try_splice(
                dropped_history=dropped, protected_top=protected_top,
                protected_bottom=protected_bottom, included_history=included,
                budget=raw_budget,
                count_messages=lambda msgs: self._count_messages(msgs, len(tools) > 0),
            )
            if result is not None:
                final_messages, included, extra_truncated = result
                truncated_count += extra_truncated

        final_count = await self._count_messages(final_messages, len(tools) > 0)
        return BuildResult(
            messages=final_messages, tokens_used=final_count, tokens_budget=raw_budget,
            truncated_count=truncated_count, kept_first_user=first_user_msg is not None,
            memory_epoch_included=memory_epoch_included,
        )

    def _render_message(self, message: Message) -> str:
        """Render a single message to the same JSON representation used by
        :meth:`InferenceClient.count_request`.
        """
        return json.dumps(message_to_dict(message))

    async def _count_tokens(self, message: Message) -> int:
        """Count tokens for a single message, with per-builder caching.

        Cache key is ``(role, content)`` so identical messages survive
        object re-creation between turns.

        ``reasoning_content`` is intentionally omitted: it is stripped
        before the prompt is sent to llama.cpp, so it does not contribute
        to the actual token count.

        ``tool_call_id`` is also omitted: the ``tool`` role prefix that
        includes it has a constant length per role, so all tool-result
        messages with the same ``content`` can safely share one cache entry.

        Args:
            message: Message to count

        Returns:
            Token count for the rendered message dict
        """
        key = (message.role, message.content or "")
        if key in self._tokenize_cache:
            self._tokenize_cache.move_to_end(key)
            return self._tokenize_cache[key]
        tokens = await self._inference.tokenize(self._render_message(message))
        count = len(tokens)
        self._tokenize_cache[key] = count
        if len(self._tokenize_cache) > 4096:
            self._tokenize_cache.popitem(last=False)
        return count

    async def _count_body(self, messages: list[Message]) -> int:
        """Count tokens for message body only (no tools).

        Always call count_request with tools=[] for consistency.

        Args:
            messages: Messages to count

        Returns:
            Raw token count for body only
        """
        # Cache static-content counts (e.g. system prompt) that rarely change.
        cache_key = hash(tuple((m.role, m.content) for m in messages))
        if cache_key == self._last_system_cache_key and self._system_token_count is not None:
            return self._system_token_count
        count = await self._inference.count_request(messages, tools=[])
        # Only cache single-message system prompts (the static prefix).
        if len(messages) == 1 and messages[0].role == "system":
            self._last_system_cache_key = cache_key
            self._system_token_count = count
        return count

    def _apply_correction(self, body_count: int, has_tools: bool) -> int:
        """Apply calibration correction to body count.

        Formula: corrected = int(body_count / body_factor) + meta_tool_overhead (if tools)

        Args:
            body_count: Raw count from count_request with no tools
            has_tools: Whether tools will be included in the actual request

        Returns:
            Corrected token count
        """
        corrected = int(body_count / self._body_factor)
        if has_tools:
            corrected += self._meta_tool_overhead
        return corrected

    async def _count_messages(self, messages: list[Message], has_tools: bool) -> int:
        """Count tokens for messages, applying calibration correction.

        Args:
            messages: Messages to count
            has_tools: Whether tools will be in the request

        Returns:
            Corrected token count
        """
        body_count = await self._count_body(messages)
        return self._apply_correction(body_count, has_tools)
