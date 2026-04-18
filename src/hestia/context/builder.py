"""ContextBuilder assembles the message list for a turn under a token budget."""

import json
from dataclasses import dataclass
from pathlib import Path

from hestia.context.compressor import HistoryCompressor
from hestia.core.inference import InferenceClient, _message_to_dict
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
        skill_index_prefix: str | None = None,
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
            skill_index_prefix: Optional skill index to prepend to system prompt
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
        self._skill_index_prefix = skill_index_prefix
        self._style_prefix = style_prefix
        self._compressor = compressor
        self._compress_on_overflow = compress_on_overflow
        self._tokenize_cache: dict[tuple[str, str], int] = {}
        self._join_overhead = 0

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

    def set_skill_index_prefix(self, skill_index_prefix: str | None) -> None:
        """Set the skill index prefix to prepend to system prompts.

        Args:
            skill_index_prefix: Skill index text, or None to clear
        """
        self._skill_index_prefix = skill_index_prefix

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
            with open(path) as f:
                data = json.load(f)
                body_factor = data.get("body_factor", 1.0)
                meta_tool_overhead = data.get("meta_tool_overhead_tokens", 0)
        else:
            body_factor = 1.0
            meta_tool_overhead = 0

        return cls(inference_client, policy, body_factor, meta_tool_overhead)

    def _prefix_layers(self) -> list[_PrefixLayer]:
        """Return prefix layers in canonical assembly order."""
        return [
            _PrefixLayer("identity", self._identity_prefix),
            _PrefixLayer("memory_epoch", self._memory_epoch_prefix),
            _PrefixLayer("skill_index", self._skill_index_prefix),
            _PrefixLayer("style", self._style_prefix),
        ]

    async def build(
        self,
        session: Session,
        history: list[Message],
        system_prompt: str,
        tools: list[ToolSchema],
        new_user_message: Message | None = None,
    ) -> BuildResult:
        """Build the message list for a new turn.

        Strategy:
        1. Start with system prompt (+ first user if in history)
        2. Add new user message (if provided)
        3. Add messages from history (newest first) until budget exhausted
        4. Never split tool_call / tool_result pairs
        5. Return messages in chronological order

        The per-message tokenize cache survives across ``build()`` calls on
        the same builder instance. If the inference client URL or model
        changes, construct a new ``ContextBuilder`` — the cache does not
        invalidate reactively.

        Args:
            session: Current session
            history: Previous messages in the session
            system_prompt: System prompt to include
            tools: Available tools (for overhead calculation)
            new_user_message: The new user message for this turn, or None for
                            continuation turns (e.g., during tool chains)

        Returns:
            BuildResult with messages and bookkeeping
        """
        # Get budget from policy
        raw_budget = self._policy.turn_token_budget(session)

        truncated_count = 0

        # Build effective system prompt from registered prefix layers
        parts = [layer.value for layer in self._prefix_layers() if layer.value]
        parts.append(system_prompt)
        effective_prompt = "\n\n".join(parts)
        memory_epoch_included = self._memory_epoch_prefix is not None

        # Create system message
        system_msg = Message(role="system", content=effective_prompt)

        # Find first user message (must be protected for Qwen template)
        first_user_msg: Message | None = None
        for msg in history:
            if msg.role == "user":
                first_user_msg = msg
                break

        # Build protected_top: system + first_user (always at start)
        protected_top: list[Message] = [system_msg]
        if first_user_msg:
            protected_top.append(first_user_msg)

        # Build protected_bottom: new_user_message (always at end, if provided)
        protected_bottom: list[Message] = []
        if new_user_message is not None:
            protected_bottom.append(new_user_message)

        # Count tokens for protected messages (body only, no tools)
        protected_body = await self._count_body(protected_top + protected_bottom)
        protected_count = self._apply_correction(protected_body, has_tools=len(tools) > 0)

        if protected_count > raw_budget:
            raise ContextTooLargeError(
                f"Protected context ({protected_count} tokens) exceeds per-slot budget "
                f"({raw_budget}). System+identity+memory_epoch+skill_index+new_user is "
                "too large to fit. Reduce identity, memory_epoch, or run /reset."
            )

        # Compute constant join-overhead once per build.
        # We measure the incremental token cost of adding a second message
        # to a single-message request body; this comma/array overhead is
        # roughly constant for each additional message beyond the protected
        # set.  Total trim-window tokens ≈
        #   sum(_count_tokens(m) for m in window) + len(window) * join_overhead
        self._join_overhead = 0
        _m1: Message | None = None
        _m2: Message | None = None
        if len(history) >= 2:
            _m1, _m2 = history[0], history[1]
        elif len(protected_top + protected_bottom) >= 2:
            _combo = protected_top + protected_bottom
            _m1, _m2 = _combo[0], _combo[1]
        if _m1 is not None and _m2 is not None:
            _single_body = json.dumps(
                {"model": self._inference.model_name, "messages": [_message_to_dict(_m1)]}
            )
            _combined_body = json.dumps(
                {
                    "model": self._inference.model_name,
                    "messages": [_message_to_dict(_m1), _message_to_dict(_m2)],
                }
            )
            _single_count = len(await self._inference.tokenize(_single_body))
            _combined_count = len(await self._inference.tokenize(_combined_body))
            self._join_overhead = (
                _combined_count - _single_count - await self._count_tokens(_m2)
            )

        # Add remaining history messages (newest first) while they fit
        included_history: list[Message] = []
        dropped_history: list[Message] = []
        window_body = 0  # cached body tokens for included_history beyond protected

        # Walk history in reverse (newest first)
        history_candidates = list(reversed(history))
        i = 0
        while i < len(history_candidates):
            msg = history_candidates[i]

            # Skip first_user (already in protected_top)
            if msg is first_user_msg:
                i += 1
                continue

            # Check if this is a tool result - if so, need to include paired tool_call
            if msg.role == "tool":
                # Find the assistant message with matching tool_call
                pair_msgs = [msg]
                found_pair = False
                for j in range(i + 1, len(history_candidates)):
                    candidate = history_candidates[j]
                    if candidate.role == "assistant" and candidate.tool_calls:
                        for tc in candidate.tool_calls:
                            if tc.id == msg.tool_call_id:
                                pair_msgs.append(candidate)
                                found_pair = True
                                break
                    if found_pair:
                        break

                if found_pair:
                    # Try to add both messages
                    pair_window_body = (
                        sum([await self._count_tokens(m) for m in pair_msgs])
                        + len(pair_msgs) * self._join_overhead
                    )
                    candidate_body = protected_body + window_body + pair_window_body
                    count = self._apply_correction(candidate_body, len(tools) > 0)
                    if count <= raw_budget:
                        included_history.extend(pair_msgs)
                        window_body += pair_window_body
                        i += len(pair_msgs)
                        continue
                    else:
                        # Can't fit pair, skip both
                        i += len(pair_msgs)
                        truncated_count += len(pair_msgs)
                        dropped_history.extend(pair_msgs)
                        continue

            # Regular message - try to add it
            msg_window_body = await self._count_tokens(msg) + self._join_overhead
            candidate_body = protected_body + window_body + msg_window_body
            count = self._apply_correction(candidate_body, len(tools) > 0)

            if count <= raw_budget:
                included_history.append(msg)
                window_body += msg_window_body
            else:
                # Doesn't fit, skip it and all older messages
                truncated_count += len(history_candidates) - i
                dropped_history.extend(history_candidates[i:])
                break

            i += 1

        # Assemble final message list in chronological order
        # system, first_user, [history in chronological order], new_user
        final_messages = list(protected_top)  # system + first_user

        # Optionally compress dropped history and splice summary
        if (
            self._compressor is not None
            and self._compress_on_overflow
            and dropped_history
        ):
            summary = await self._compressor.summarize(list(reversed(dropped_history)))
            if summary:
                summary_msg = Message(
                    role="system",
                    content=f"[PRIOR CONTEXT SUMMARY]\n{summary}",
                )
                # Insert right after system_msg (index 0)
                test_with_summary = list(final_messages)
                test_with_summary.insert(1, summary_msg)
                summary_count = await self._count_messages(
                    test_with_summary, len(tools) > 0
                )
                if summary_count <= raw_budget:
                    final_messages.insert(1, summary_msg)
                else:
                    # Retry once: drop oldest included message and try again
                    if included_history:
                        included_history.pop()
                        test_with_summary = list(final_messages)
                        # Rebuild without oldest
                        test_with_summary = list(protected_top)
                        test_with_summary.insert(1, summary_msg)
                        test_with_summary.extend(reversed(included_history))
                        test_with_summary.extend(protected_bottom)
                        summary_count = await self._count_messages(
                            test_with_summary, len(tools) > 0
                        )
                        if summary_count <= raw_budget:
                            final_messages = test_with_summary
                            truncated_count += 1
                        # else: fall back to no compression

        # Add included history in chronological order (reverse back)
        final_messages.extend(reversed(included_history))

        # Add protected_bottom at the end (new_user if provided)
        final_messages.extend(protected_bottom)

        # Count final tokens
        final_count = await self._count_messages(final_messages, len(tools) > 0)

        return BuildResult(
            messages=final_messages,
            tokens_used=final_count,
            tokens_budget=raw_budget,
            truncated_count=truncated_count,
            kept_first_user=first_user_msg is not None,
            memory_epoch_included=memory_epoch_included,
        )

    def _render_message(self, message: Message) -> str:
        """Render a single message to the same JSON representation used by
        :meth:`InferenceClient.count_request`.
        """
        return json.dumps(_message_to_dict(message))

    async def _count_tokens(self, message: Message) -> int:
        """Count tokens for a single message, with per-builder caching.

        Cache key is ``(role, content)`` so identical messages survive
        object re-creation between turns.

        Args:
            message: Message to count

        Returns:
            Token count for the rendered message dict
        """
        key = (message.role, message.content or "")
        if key in self._tokenize_cache:
            return self._tokenize_cache[key]
        tokens = await self._inference.tokenize(self._render_message(message))
        count = len(tokens)
        self._tokenize_cache[key] = count
        return count

    async def _count_body(self, messages: list[Message]) -> int:
        """Count tokens for message body only (no tools).

        Always call count_request with tools=[] for consistency.

        Args:
            messages: Messages to count

        Returns:
            Raw token count for body only
        """
        return await self._inference.count_request(messages, tools=[])

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
