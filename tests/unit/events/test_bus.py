"""Unit tests for EventBus."""

from __future__ import annotations

from typing import Any

import pytest

from hestia.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    """Return a fresh EventBus instance."""
    return EventBus()


class TestSubscribe:
    """Tests for subscribe method."""

    @pytest.mark.asyncio
    async def test_single_subscriber(self, bus: EventBus) -> None:
        """A single subscriber receives the published event."""
        received: list[tuple[str, Any]] = []

        async def handler(event_type: str, payload: Any) -> None:
            received.append((event_type, payload))

        bus.subscribe("test_event", handler)
        await bus.publish("test_event", {"key": "value"})
        await bus.drain()

        assert len(received) == 1
        assert received[0] == ("test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, bus: EventBus) -> None:
        """Multiple subscribers all receive the event (fan-out)."""
        received1: list[Any] = []
        received2: list[Any] = []

        async def handler1(_event_type: str, payload: Any) -> None:
            received1.append(payload)

        async def handler2(_event_type: str, payload: Any) -> None:
            received2.append(payload)

        bus.subscribe("test_event", handler1)
        bus.subscribe("test_event", handler2)
        await bus.publish("test_event", "payload")
        await bus.drain()

        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0] == "payload"
        assert received2[0] == "payload"

    @pytest.mark.asyncio
    async def test_different_event_types_isolated(self, bus: EventBus) -> None:
        """Subscribers for different event types do not cross-pollinate."""
        received: list[Any] = []

        async def handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("event_a", handler)
        await bus.publish("event_b", "should not arrive")
        await bus.drain()

        assert received == []


class TestPublish:
    """Tests for publish method."""

    @pytest.mark.asyncio
    async def test_no_subscribers_no_crash(self, bus: EventBus) -> None:
        """Publishing with no subscribers is a no-op."""
        await bus.publish("unknown_event", None)
        await bus.drain()
        # No exception means success

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_propagate(self, bus: EventBus) -> None:
        """A failing handler does not crash the bus or other handlers."""
        received: list[Any] = []

        async def bad_handler(_event_type: str, _payload: Any) -> None:
            raise RuntimeError("boom")

        async def good_handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("test_event", bad_handler)
        bus.subscribe("test_event", good_handler)
        await bus.publish("test_event", "safe")
        await bus.drain()

        assert received == ["safe"]


class TestDrain:
    """Tests for drain method."""

    @pytest.mark.asyncio
    async def test_awaits_pending_tasks(self, bus: EventBus) -> None:
        """Drain awaits all pending publish tasks."""
        received: list[Any] = []

        async def handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("test_event", handler)
        await bus.publish("test_event", "hello")
        await bus.drain()

        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_task_retention_and_cleanup(self, bus: EventBus) -> None:
        """Tasks are retained while running and removed after drain."""
        handler_called = False

        async def handler(_event_type: str, _payload: Any) -> None:
            nonlocal handler_called
            handler_called = True

        bus.subscribe("test_event", handler)
        await bus.publish("test_event", "x")

        # Task should be in the set before drain completes
        assert len(bus._tasks) > 0

        await bus.drain()

        assert handler_called
        assert len(bus._tasks) == 0


class TestEventTypes:
    """Tests for known event types."""

    @pytest.mark.asyncio
    async def test_schedule_fired(self, bus: EventBus) -> None:
        """schedule_fired events are delivered."""
        received: list[Any] = []

        async def handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("schedule_fired", handler)
        await bus.publish("schedule_fired", {"task_id": "t1"})
        await bus.drain()

        assert len(received) == 1
        assert received[0] == {"task_id": "t1"}

    @pytest.mark.asyncio
    async def test_chat_command(self, bus: EventBus) -> None:
        """chat_command events are delivered."""
        received: list[Any] = []

        async def handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("chat_command", handler)
        await bus.publish("chat_command", {"command": "status"})
        await bus.drain()

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_webhook_received(self, bus: EventBus) -> None:
        """webhook_received events are delivered."""
        received: list[Any] = []

        async def handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("webhook_received", handler)
        await bus.publish("webhook_received", {"endpoint": "/hook"})
        await bus.drain()

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_message_matched(self, bus: EventBus) -> None:
        """message_matched events are delivered."""
        received: list[Any] = []

        async def handler(_event_type: str, payload: Any) -> None:
            received.append(payload)

        bus.subscribe("message_matched", handler)
        await bus.publish("message_matched", {"text": "hello"})
        await bus.drain()

        assert len(received) == 1
