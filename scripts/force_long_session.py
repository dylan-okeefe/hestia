#!/usr/bin/env python3
"""Force a long session to verify context-overflow handling.

Run from repo root:
    uv run python scripts/force_long_session.py

This creates a session with a tiny context budget and feeds it messages until
the protected block exceeds budget, triggering ContextTooLargeError.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from hestia.context.builder import ContextBuilder
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.errors import ContextTooLargeError
from hestia.policy.default import DefaultPolicyEngine


async def main() -> None:
    inference = AsyncMock()
    # Token counting: each message costs len(content.split()) tokens
    inference.count_request = AsyncMock(
        side_effect=lambda msgs, tools: sum(
            len((m.content or "").split()) for m in msgs
        )
    )

    policy = DefaultPolicyEngine(ctx_window=50)  # tiny budget
    builder = ContextBuilder(inference, policy)

    session = Session(
        id="test-overflow",
        platform="cli",
        platform_user="user",
        started_at=__import__("datetime").datetime.now(),
        last_active_at=__import__("datetime").datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    history: list[Message] = []
    for i in range(20):
        history.append(Message(role="user", content=f"Message number {i} with some words."))
        history.append(Message(role="assistant", content=f"Response number {i} also has words."))

    try:
        await builder.build(
            session=session,
            history=history,
            system_prompt="You are a helpful assistant. " * 10,  # ~50 tokens
            tools=[],
            new_user_message=Message(role="user", content="Final question?"),
        )
        print("ERROR: Expected ContextTooLargeError was not raised")
    except ContextTooLargeError as exc:
        print(f"OK: ContextTooLargeError raised as expected")
        print(f"    {exc}")


if __name__ == "__main__":
    asyncio.run(main())
