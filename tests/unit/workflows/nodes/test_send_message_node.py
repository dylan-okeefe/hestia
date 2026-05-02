"""Tests for SendMessageNode."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hestia.app import AppContext
from hestia.config import HestiaConfig
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.send_message import SendMessageNode


@pytest.fixture
def app() -> AppContext:
    app = MagicMock(spec=AppContext)
    app.config = HestiaConfig.default()
    return app  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_sends_message_with_legacy_fields(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={
            "platform": "matrix",
            "user": "@user:matrix.org",
            "text": "Hello",
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
        "platform": "matrix",
        "user": "@user:matrix.org",
        "text": "Hello",
    }
    mock_send.assert_awaited_once_with("matrix", "@user:matrix.org", "Hello")


@pytest.mark.asyncio
async def test_sends_message_with_new_fields(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={
            "platform": "matrix",
            "target_user": "@user:matrix.org",
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
        "platform": "matrix",
        "user": "@user:matrix.org",
        "text": "Hello",
    }
    mock_send.assert_awaited_once_with("matrix", "@user:matrix.org", "Hello")


@pytest.mark.asyncio
async def test_uses_inputs_over_config(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"platform": "telegram", "target_user": "123", "message": "Config"},
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        executor = SendMessageNode()
        result = await executor.execute(
            app, node, {"message": "Override", "target_user": "456"}
        )

    assert result["text"] == "Override"
    assert result["user"] == "456"
    mock_send.assert_awaited_once_with("telegram", "456", "Override")


@pytest.mark.asyncio
async def test_uses_legacy_inputs_over_config(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"platform": "telegram", "user": "123", "text": "Config"},
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        executor = SendMessageNode()
        result = await executor.execute(
            app, node, {"text": "Override", "user": "456"}
        )

    assert result["text"] == "Override"
    assert result["user"] == "456"
    mock_send.assert_awaited_once_with("telegram", "456", "Override")


@pytest.mark.asyncio
async def test_new_fields_preferred_over_legacy_in_inputs(app: AppContext) -> None:
    """When both new and legacy keys are present in inputs, new keys win."""
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"platform": "telegram"},
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        executor = SendMessageNode()
        result = await executor.execute(
            app,
            node,
            {"target_user": "new", "user": "legacy", "message": "new_msg", "text": "legacy_msg"},
        )

    assert result["user"] == "new"
    assert result["text"] == "new_msg"
    mock_send.assert_awaited_once_with("telegram", "new", "new_msg")


@pytest.mark.asyncio
async def test_missing_platform_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"target_user": "123", "message": "hi"},
    )
    executor = SendMessageNode()
    with pytest.raises(ValueError, match="platform"):
        await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_missing_user_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"platform": "matrix", "message": "hi"},
    )
    executor = SendMessageNode()
    with pytest.raises(ValueError, match="target_user"):
        await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_missing_text_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"platform": "matrix", "target_user": "123"},
    )
    executor = SendMessageNode()
    with pytest.raises(ValueError, match="message"):
        await executor.execute(app, node, {})
