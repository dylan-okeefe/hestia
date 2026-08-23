"""Compressed summary strategy for ContextBuilder."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from hestia.context.compressor import HistoryCompressor
from hestia.context.sequence_validator import validate_chat_template_sequence
from hestia.core.types import Message


class CompressedSummaryStrategy:
    """Strategy for compressing dropped history and splicing a summary."""

    def __init__(self, compressor: HistoryCompressor) -> None:
        self._compressor = compressor

    async def try_splice(
        self,
        dropped_history: list[Message],
        protected_top: list[Message],
        protected_bottom: list[Message],
        included_history: list[Message],
        budget: int,
        count_messages: Callable[[list[Message]], Awaitable[int]],
    ) -> tuple[list[Message], list[Message], int] | None:
        """Compress *dropped_history* and try to insert the summary.

        If the summary does not fit, the strategy retries once by dropping
        the oldest message from *included_history*.

        Args:
            dropped_history: Messages that were removed from context, in
                chronological order.
            protected_top: Messages that are always at the start of context
                (e.g. system prompt + first user message).
            protected_bottom: Messages that are always at the end of context
                (e.g. the new user message).
            included_history: Currently selected history messages in
                chronological order.
            budget: Total token budget.
            count_messages: Async callable that returns the corrected token
                count for a list of messages.

        Returns:
            A 3-tuple of *(messages, updated_included_history, extra_truncated)*
            when the summary fits, or ``None`` if it could not be inserted.
        """
        summary = await self._compressor.summarize(dropped_history)
        if not summary:
            return None

        # Merge the summary into the existing system prompt so we never
        # emit a second system message — strict chat templates (e.g. Qwen)
        # raise "System message must be at the beginning" when they see one.
        original_system = protected_top[0]
        augmented_system = Message(
            role="system",
            content=f"{original_system.content}\n\n[PRIOR CONTEXT SUMMARY]\n{summary}",
        )

        # Try inserting right after the system message (index 0).
        # Re-validate after splicing (BUG-028): compression must never emit a
        # sequence strict chat templates would reject.
        messages = validate_chat_template_sequence(
            [
                augmented_system,
                *protected_top[1:],
                *included_history,
                *protected_bottom,
            ]
        )

        count = await count_messages(messages)
        if count <= budget:
            return messages, included_history, 0

        # Retry once: drop the oldest included message (pair-aware — an
        # assistant owning tool results takes them with it).
        if included_history:
            retry_included = list(included_history)
            removed = retry_included.pop(0)
            if removed.role == "assistant" and removed.tool_calls:
                owned = {tc.id for tc in removed.tool_calls if tc.id}
                while (
                    retry_included
                    and retry_included[0].role == "tool"
                    and retry_included[0].tool_call_id in owned
                ):
                    retry_included.pop(0)
            messages = validate_chat_template_sequence(
                [
                    augmented_system,
                    *protected_top[1:],
                    *retry_included,
                    *protected_bottom,
                ]
            )

            count = await count_messages(messages)
            if count <= budget:
                return messages, retry_included, 1

        return None
