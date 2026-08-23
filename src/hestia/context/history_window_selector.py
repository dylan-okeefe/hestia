"""History window selection logic for ContextBuilder."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from hestia.core.types import Message


class HistoryWindowSelector:
    """Selects a window of recent history messages that fit within a token budget."""

    async def select(
        self,
        history: list[Message],
        budget: int,
        token_counter: Callable[[Message], Awaitable[int]],
        skip_message: Message | None = None,
    ) -> tuple[list[Message], list[Message], int]:
        """Select history messages newest-first until budget exhausted.

        Never splits a tool_call / tool_result pair.

        Args:
            history: Full conversation history in chronological order.
            budget: Available token budget for history messages (after protected
                messages have been accounted for).
            token_counter: Async callable returning token count for a single
                message. Should include any per-message join overhead.
            skip_message: Optional message to skip (e.g. first user message
                that is already protected and should not be re-selected).

        Returns:
            A 3-tuple of *(included, dropped, truncated_count)* where
            ``included`` is the selected messages in chronological order,
            ``dropped`` is the messages that did not fit in chronological
            order, and ``truncated_count`` is the number of dropped messages.
        """
        included_history: list[Message] = []
        dropped_history: list[Message] = []
        truncated_count = 0
        window_body = 0

        history_candidates = list(reversed(history))
        i = 0
        while i < len(history_candidates):
            msg = history_candidates[i]

            if msg is skip_message:
                i += 1
                continue

            if msg.role == "tool":
                # Find the assistant message owning this tool call. In
                # reversed order every sibling tool result of the same
                # assistant sits between this result and that assistant, so
                # the atomic group is candidates[i .. pair_end] (BUG-027:
                # advancing by pair length used to skip siblings entirely
                # and double-count the shared assistant).
                pair_end: int | None = None
                for j in range(i + 1, len(history_candidates)):
                    candidate = history_candidates[j]
                    if (
                        candidate.role == "assistant"
                        and candidate.tool_calls
                        and any(tc.id == msg.tool_call_id for tc in candidate.tool_calls)
                    ):
                        pair_end = j
                        break

                if pair_end is not None:
                    group = history_candidates[i : pair_end + 1]
                    group_counts = await asyncio.gather(
                        *(token_counter(m) for m in group)
                    )
                    group_total = sum(group_counts)
                    if window_body + group_total <= budget:
                        included_history.extend(group)
                        window_body += group_total
                    else:
                        truncated_count += len(group)
                        dropped_history.extend(group)
                    i = pair_end + 1
                    continue

            msg_window_body = await token_counter(msg)
            if window_body + msg_window_body <= budget:
                included_history.append(msg)
                window_body += msg_window_body
            else:
                # BUG-072: the protected first user message may sit later in
                # the candidate slice; it must not be reported as dropped.
                remaining = [
                    m for m in history_candidates[i:] if m is not skip_message
                ]
                truncated_count += len(remaining)
                dropped_history.extend(remaining)
                break

            i += 1

        return (
            list(reversed(included_history)),
            list(reversed(dropped_history)),
            truncated_count,
        )
