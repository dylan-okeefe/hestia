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
        calibration_factor: float = 1.0,
    ):
        """Initialize with inference client and policy.

        Args:
            inference_client: Client for token counting
            policy: Policy engine for budget decisions
            calibration_factor: Correction factor for count_request() over-counting.
                              Multiply count_request result by (1/calibration_factor)
                              to get corrected count.
        """
        self._inference = inference_client
        self._policy = policy
        self._calibration = calibration_factor

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
            ContextBuilder with loaded calibration factor
        """
        path = calibration_path or Path("docs/calibration.json")
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                factor = data.get("correction_factor", 1.0)
        else:
            factor = 1.0

        return cls(inference_client, policy, factor)

    async def build(
        self,
        session: Session,
        history: list[Message],
        new_user_message: Message,
        system_prompt: str,
        tools: list[ToolSchema],
    ) -> BuildResult:
        """Build the message list for a new turn.

        Strategy:
        1. Start with system prompt + new user message
        2. Find and protect the first user message from history
        3. Add messages from history (newest first) until budget exhausted
        4. Never split tool_call / tool_result pairs
        5. Return messages in chronological order

        Args:
            session: Current session
            history: Previous messages in the session
            new_user_message: The new user message for this turn
            system_prompt: System prompt to include
            tools: Available tools (for token counting)

        Returns:
            BuildResult with messages and bookkeeping
        """
        # Get budget from policy
        raw_budget = self._policy.turn_token_budget(session)

        truncated_count = 0

        # Create system message
        system_msg = Message(role="system", content=system_prompt)

        # Find first user message (must be protected for Qwen template)
        first_user_msg: Message | None = None
        for msg in history:
            if msg.role == "user":
                first_user_msg = msg
                break

        # Start with protected messages
        protected = [system_msg]
        if first_user_msg:
            protected.append(first_user_msg)
        protected.append(new_user_message)

        # Count tokens for protected messages
        protected_count = await self._count_messages(protected, tools)

        if protected_count > raw_budget:
            # Even protected messages don't fit - this is bad
            # Return just system + new_user as best effort
            return BuildResult(
                messages=[system_msg, new_user_message],
                tokens_used=await self._count_messages([system_msg, new_user_message], tools),
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

            # Skip first_user (already in protected)
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
                    test_messages = protected + included_history + pair_msgs
                    count = await self._count_messages(test_messages, tools)
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
            test_messages = protected + included_history + [msg]
            count = await self._count_messages(test_messages, tools)

            if count <= raw_budget:
                included_history.append(msg)
            else:
                # Doesn't fit, skip it and all older messages
                truncated_count += len(history_candidates) - i
                break

            i += 1

        # Assemble final message list in chronological order
        # system, first_user, [history in chronological order], new_user
        final_messages = [system_msg]
        if first_user_msg:
            final_messages.append(first_user_msg)

        # Add included history in chronological order (reverse back)
        final_messages.extend(reversed(included_history))

        # Add new user message at the end
        final_messages.append(new_user_message)

        # Count final tokens
        final_count = await self._count_messages(final_messages, tools)

        return BuildResult(
            messages=final_messages,
            tokens_used=final_count,
            tokens_budget=raw_budget,
            truncated_count=truncated_count,
            kept_first_user=first_user_msg is not None,
        )

    async def _count_messages(self, messages: list[Message], tools: list[ToolSchema]) -> int:
        """Count tokens for messages, applying calibration correction.

        Args:
            messages: Messages to count
            tools: Tools (included in count)

        Returns:
            Corrected token count
        """
        raw_count = await self._inference.count_request(messages, tools)
        # Apply calibration: count_request over-counts, so divide by factor
        corrected = int(raw_count / self._calibration)
        return corrected
