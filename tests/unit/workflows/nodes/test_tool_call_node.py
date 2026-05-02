"""Tests for ToolCallNode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.app import AppContext
from hestia.tools.types import ToolCallResult
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.tool_call import ToolCallNode


@pytest.fixture
def app() -> AppContext:
    app = MagicMock(spec=AppContext)
    app.tool_registry = AsyncMock()
    return app  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_calls_tool_by_name(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="tool_call",
        label="Call Echo",
        config={"tool_name": "echo"},
    )
    app.tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="hello",
            artifact_handle=None,
            truncated=False,
        )
    )

    executor = ToolCallNode()
    result = await executor.execute(app, node, {"text": "hi"})

    assert result == "hello"
    app.tool_registry.call.assert_awaited_once_with("echo", {"text": "hi"})


@pytest.mark.asyncio
async def test_missing_tool_name_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="tool_call",
        label="No Tool",
        config={},
    )
    executor = ToolCallNode()
    with pytest.raises(ValueError, match="tool_name"):
        await executor.execute(app, node, {})
