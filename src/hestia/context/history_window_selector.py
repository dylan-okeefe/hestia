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
                    pair_token_counts = await asyncio.gather(
                        *(token_counter(m) for m in pair_msgs)
                    )
                    pair_window_body = sum(pair_token_counts)
                    if window_body + pair_window_body <= budget:
                        included_history.extend(pair_msgs)
                        window_body += pair_window_body
                        i += len(pair_msgs)
                        continue
                    else:
                        i += len(pair_msgs)
                        truncated_count += len(pair_msgs)
                        dropped_history.extend(pair_msgs)
                        continue

            msg_window_body = await token_counter(msg)
            if window_body + msg_window_body <= budget:
                included_history.append(msg)
                window_body += msg_window_body
            else:
                truncated_count += len(history_candidates) - i
                dropped_history.extend(history_candidates[i:])
                break

            i += 1

        return (
            list(reversed(included_history)),
            list(reversed(dropped_history)),
            truncated_count,
        )
