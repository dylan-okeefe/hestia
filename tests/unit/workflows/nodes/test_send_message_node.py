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
async def test_config_wins_over_inputs(app: AppContext) -> None:
    """SEC-022: destinations pinned in node config take precedence over
    trigger-supplied inputs, so attacker-controlled payloads cannot choose
    the recipient."""
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={"platform": "telegram", "target_user": "123"},
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        executor = SendMessageNode()
        result = await executor.execute(
            app, node, {"message": "Payload text", "target_user": "456"}
        )

    assert result["text"] == "Payload text"  # content may come from inputs
    assert result["user"] == "123"  # destination may not
    mock_send.assert_awaited_once_with("telegram", "123", "Payload text")


@pytest.mark.asyncio
async def test_config_wins_over_legacy_inputs(app: AppContext) -> None:
    """SEC-022: same precedence rule for the legacy field names."""
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

    assert result["text"] == "Override"  # text still resolves inputs-first
    assert result["user"] == "123"  # destination pinned in config wins
    mock_send.assert_awaited_once_with("telegram", "123", "Override")


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
async def test_target_conversation_preferred_over_target_user(app: AppContext) -> None:
    """target_conversation is used as the destination when provided."""
    node = WorkflowNode(
        id="n1",
        type="send_message",
        label="Notify",
        config={
            "platform": "telegram",
            "target_conversation": "-5180445128",
            "target_user": "legacy_user",
            "message": "Hello",
        },
    )

    with patch(
        "hestia.workflows.nodes.send_message.PlatformNotifier.send",
        return_value=True,
    ) as mock_send:
        executor = SendMessageNode()
        result = await executor.execute(app, node, {})

    assert result["user"] == "-5180445128"
    assert result["text"] == "Hello"
    mock_send.assert_awaited_once_with("telegram", "-5180445128", "Hello")


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
