"""ContextBuilder assembles the message list for a turn under a token budget."""

import json
from dataclasses import dataclass
from pathlib import Path

from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session, ToolSchema
from hestia.policy.engine import PolicyEngine


@dataclass
class BuildResult:
    """Result of building context for a turn."""

    messages: list[Message]
    tokens_used: int
    tokens_budget: int
    truncated_count: int  # how many historical messages got dropped
    kept_first_user: bool  # sanity flag for the Qwen template requirement


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
    ):
        """Initialize with inference client and policy.

        Args:
            inference_client: Client for token counting
            policy: Policy engine for budget decisions
            body_factor: Correction factor for message body tokenization
            meta_tool_overhead: Constant overhead when tools are present
            identity_prefix: Optional compiled identity view to prepend to system prompt
        """
        self._inference = inference_client
        self._policy = policy
        self._body_factor = body_factor
        self._meta_tool_overhead = meta_tool_overhead
        self._identity_prefix = identity_prefix

    def set_identity_prefix(self, identity_prefix: str | None) -> None:
        """Set the identity prefix to prepend to system prompts.

        Args:
            identity_prefix: Compiled identity view, or None to clear
        """
        self._identity_prefix = identity_prefix

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

    async def build(
        self,
        session: Session,
        history: list[Message],
        system_prompt: str,
        tools: list[ToolSchema],
        new_user_message: Message | None = None,
        identity_prefix: str | None = None,
    ) -> BuildResult:
        """Build the message list for a new turn.

        Strategy:
        1. Start with system prompt (+ first user if in history)
        2. Add new user message (if provided)
        3. Add messages from history (newest first) until budget exhausted
        4. Never split tool_call / tool_result pairs
        5. Return messages in chronological order

        Args:
            session: Current session
            history: Previous messages in the session
            system_prompt: System prompt to include
            tools: Available tools (for overhead calculation)
            new_user_message: The new user message for this turn, or None for
                            continuation turns (e.g., during tool chains)
            identity_prefix: Optional compiled identity view to prepend to system prompt

        Returns:
            BuildResult with messages and bookkeeping
        """
        # Get budget from policy
        raw_budget = self._policy.turn_token_budget(session)

        truncated_count = 0

        # Build effective system prompt with optional identity prefix
        # Use provided identity_prefix, fall back to stored one
        effective_identity = identity_prefix if identity_prefix is not None else self._identity_prefix
        effective_prompt = system_prompt
        if effective_identity:
            effective_prompt = effective_identity + "\n\n" + system_prompt

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
            # Even protected messages don't fit - this is bad
            # Return just system (+ new_user if available) as best effort
            best_effort = [system_msg]
            if new_user_message is not None:
                best_effort.append(new_user_message)
            return BuildResult(
                messages=best_effort,
                tokens_used=await self._count_messages(best_effort, len(tools) > 0),
                tokens_budget=raw_budget,
                truncated_count=len(history),
                kept_first_user=False,
            )

        # Add remaining history messages (newest first) while they fit
        included_history: list[Message] = []

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
                    test_messages = protected_top + included_history + pair_msgs + protected_bottom
                    count = await self._count_messages(test_messages, len(tools) > 0)
                    if count <= raw_budget:
                        included_history.extend(pair_msgs)
                        i += len(pair_msgs)
                        continue
                    else:
                        # Can't fit pair, skip both
                        i += len(pair_msgs)
                        truncated_count += len(pair_msgs)
                        continue

            # Regular message - try to add it
            test_messages = protected_top + included_history + [msg] + protected_bottom
            count = await self._count_messages(test_messages, len(tools) > 0)

            if count <= raw_budget:
                included_history.append(msg)
            else:
                # Doesn't fit, skip it and all older messages
                truncated_count += len(history_candidates) - i
                break

            i += 1

        # Assemble final message list in chronological order
        # system, first_user, [history in chronological order], new_user
        final_messages = list(protected_top)  # system + first_user

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
        )

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
