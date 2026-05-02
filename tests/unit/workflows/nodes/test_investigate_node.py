"""Tests for InvestigateNode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.app import AppContext
from hestia.core.types import ChatResponse
from hestia.tools.types import ToolCallResult
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.investigate import InvestigateNode


@pytest.fixture
def app() -> AppContext:
    app = MagicMock(spec=AppContext)
    app.inference = AsyncMock()
    app.tool_registry = AsyncMock()
    return app  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_shallow_investigation_returns_report(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Investigate",
        config={"topic": "best Python web frameworks"},
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"findings": ["Django is batteries-included", "FastAPI is async-native"], "recommendations": ["Use FastAPI for microservices"], "sources": ["docs.djangoproject.com"]}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=50,
            completion_tokens=30,
            total_tokens=80,
        )
    )

    executor = InvestigateNode()
    result = await executor.execute(app, node, {})

    assert result["topic"] == "best Python web frameworks"
    assert len(result["findings"]) == 2
    assert "Django is batteries-included" in result["findings"]
    assert result["recommendations"] == ["Use FastAPI for microservices"]
    assert result["sources"] == ["docs.djangoproject.com"]
    app.inference.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_deep_investigation_makes_multiple_calls(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Deep Investigate",
        config={"topic": "AI safety", "depth": "deep"},
    )
    app.inference.chat = AsyncMock(
        side_effect=[
            ChatResponse(
                content='{"findings": ["Alignment is hard"], "recommendations": [], "sources": ["arxiv.org"]}',
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=40,
                completion_tokens=20,
                total_tokens=60,
            ),
            ChatResponse(
                content='{"findings": ["Interpretability helps"], "recommendations": ["Fund mechanistic interpretability"], "sources": ["distill.pub"]}',
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=40,
                completion_tokens=20,
                total_tokens=60,
            ),
            ChatResponse(
                content='{"findings": [], "recommendations": [], "sources": []}',
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=40,
                completion_tokens=10,
                total_tokens=50,
            ),
        ]
    )

    executor = InvestigateNode()
    result = await executor.execute(app, node, {})

    assert result["topic"] == "AI safety"
    assert len(result["findings"]) == 2
    assert "Alignment is hard" in result["findings"]
    assert "Interpretability helps" in result["findings"]
    assert "Fund mechanistic interpretability" in result["recommendations"]
    assert app.inference.chat.await_count == 3


@pytest.mark.asyncio
async def test_with_specified_tools_calls_those_tools(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Tool Investigate",
        config={"topic": "weather today", "tools": ["weather_lookup"]},
    )
    app.tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="Sunny, 72°F",
            artifact_handle=None,
            truncated=False,
        )
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"findings": ["It is sunny today"], "recommendations": ["Wear sunglasses"], "sources": ["weather_lookup"]}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=30,
            completion_tokens=20,
            total_tokens=50,
        )
    )

    executor = InvestigateNode()
    result = await executor.execute(app, node, {})

    assert result["topic"] == "weather today"
    assert "It is sunny today" in result["findings"]
    app.tool_registry.call.assert_awaited_once_with("weather_lookup", {})


@pytest.mark.asyncio
async def test_missing_topic_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="No Topic",
        config={},
    )
    executor = InvestigateNode()
    with pytest.raises(ValueError, match="topic"):
        await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_falls_back_to_raw_content_on_bad_json(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Bad JSON",
        config={"topic": "foo"},
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content="This is not JSON",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    executor = InvestigateNode()
    result = await executor.execute(app, node, {})

    assert result["topic"] == "foo"
    assert result["findings"] == ["This is not JSON"]
    assert result["recommendations"] == []
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_tool_failure_gracefully_handled(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Failing Tool",
        config={"topic": "stock price", "tools": ["stock_api"]},
    )
    app.tool_registry.call = AsyncMock(side_effect=RuntimeError("API down"))
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"findings": ["Tool failed"], "recommendations": [], "sources": []}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
        )
    )

    executor = InvestigateNode()
    result = await executor.execute(app, node, {})

    assert result["findings"] == ["Tool failed"]
    app.tool_registry.call.assert_awaited_once_with("stock_api", {})
