"""In-memory async event bus with typed fan-out."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, Any], Awaitable[None]]


class EventBus:
    """Async pub/sub event bus.

    Subscribers register async handlers per event type.  Published events
    are fan-out to *all* matching handlers concurrently.
    """

    def __init__(self) -> None:
        """Initialize an empty event bus."""
        self._handlers: dict[str, list[EventHandler]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an async handler for an event type.

        Args:
            event_type: The event type to subscribe to.
            handler: Async callable ``(event_type, payload) -> None``.
        """
        self._handlers.setdefault(event_type, [])
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, payload: Any) -> None:
        """Publish an event to all subscribers (fire-and-forget).

        Args:
            event_type: The type of event being published.
            payload: Arbitrary event payload.
        """
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.debug("No handlers for event type %r", event_type)
            return

        for handler in handlers:
            task = asyncio.create_task(
                self._invoke_handler(handler, event_type, payload),
                name=f"eventbus-{event_type}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Await all pending publish tasks."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _invoke_handler(
        self, handler: EventHandler, event_type: str, payload: Any
    ) -> None:
        try:
            await handler(event_type, payload)
        except Exception:
            logger.exception("Event handler failed for %r", event_type)
