"""Tests for SendMessageNode interactive mode."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from hestia.app import AppContext
from hestia.config import HestiaConfig
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.send_message import SendMessageNode
from hestia.workflows.response_store import WorkflowResponseStore


@pytest.fixture
def app() -> AppContext:
    app = MagicMock(spec=AppContext)
    app.config = HestiaConfig.default()
    return app  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_interactive_buttons_sends_and_waits(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Ask",
        config={
            "platform": "telegram",
            "target_user": "123",
            "message": "Approve this?",
            "requires_response": True,
            "response_type": "buttons",
            "buttons": ["Approve", "Deny"],
            "timeout_seconds": 5,
        },
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send_interactive",
        return_value=True,
    ) as mock_send:
        store = WorkflowResponseStore()
        with patch(
            "hestia.workflows.nodes.send_message.DEFAULT_RESPONSE_STORE",
            store,
        ):
            executor = SendMessageNode()
            # Resolve the response asynchronously after a short delay
            def _resolve_later() -> None:
                req_id = next(iter(store._pending.keys()))
                store.resolve(req_id, "Approve")

            asyncio.get_running_loop().call_later(0.05, _resolve_later)
            result = await executor.execute(app, node, {})

    assert result["sent"] is True
    assert result["response"] == "Approve"
    assert result["timed_out"] is False
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_interactive_timeout(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Ask",
        config={
            "platform": "telegram",
            "target_user": "123",
            "message": "Approve this?",
            "requires_response": True,
            "response_type": "buttons",
            "timeout_seconds": 0.01,
        },
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send_interactive",
        return_value=True,
    ):
        store = WorkflowResponseStore()
        with patch(
            "hestia.workflows.nodes.send_message.DEFAULT_RESPONSE_STORE",
            store,
        ):
            executor = SendMessageNode()
            result = await executor.execute(app, node, {})

    assert result["sent"] is True
    assert result["response"] is None
    assert result["timed_out"] is True


@pytest.mark.asyncio
async def test_interactive_free_text_fallback(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Ask",
        config={
            "platform": "matrix",
            "target_user": "!room:matrix.org",
            "message": "What is your name?",
            "requires_response": True,
            "response_type": "free_text",
            "timeout_seconds": 5,
        },
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        store = WorkflowResponseStore()
        with patch(
            "hestia.workflows.nodes.send_message.DEFAULT_RESPONSE_STORE",
            store,
        ):
            executor = SendMessageNode()

            def _resolve_later() -> None:
                req_id = next(iter(store._pending.keys()))
                store.resolve(req_id, "Alice")

            asyncio.get_running_loop().call_later(0.05, _resolve_later)
            result = await executor.execute(app, node, {})

    assert result["sent"] is True
    assert result["response"] == "Alice"
    assert result["timed_out"] is False
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_interactive_send_unchanged(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={
            "platform": "telegram",
            "target_user": "123",
            "message": "Hello",
        },
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        executor = SendMessageNode()
        result = await executor.execute(app, node, {})

    assert result == {
        "sent": True,
        "platform": "telegram",
        "user": "123",
        "text": "Hello",
    }
    mock_send.assert_awaited_once_with("telegram", "123", "Hello")


@pytest.mark.asyncio
async def test_interactive_telegram_non_numeric_user_raises(app: AppContext) -> None:
    """Passing a Matrix room ID to Telegram interactive send raises ValueError."""
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Ask",
        config={
            "platform": "telegram",
            "target_user": "!room:matrix.org",
            "message": "Approve this?",
            "requires_response": True,
            "response_type": "buttons",
            "buttons": ["Approve", "Deny"],
            "timeout_seconds": 5,
        },
    )

    executor = SendMessageNode()
    with pytest.raises(ValueError, match="Invalid Telegram chat ID"):
        await executor.execute(app, node, {})
