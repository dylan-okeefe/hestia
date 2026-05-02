"""Tests for LLMDecisionNode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.app import AppContext
from hestia.core.types import ChatResponse
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.llm_decision import LLMDecisionNode


@pytest.fixture
def app() -> AppContext:
    app = MagicMock(spec=AppContext)
    app.inference = AsyncMock()
    return app  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_selects_branch(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="llm_decision",
        label="Decide",
        config={"branches": ["a", "b"], "prompt": "Pick one"},
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content="a",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
    )

    executor = LLMDecisionNode()
    result = await executor.execute(app, node, {"value": 42})

    assert result.content == "a"
    app.inference.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_returns_raw_when_no_branches(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="llm_decision",
        label="Decide",
        config={},
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content="yes",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
    )

    executor = LLMDecisionNode()
    result = await executor.execute(app, node, {})

    assert result.content == "yes"
