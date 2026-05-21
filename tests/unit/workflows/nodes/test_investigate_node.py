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


@pytest.mark.asyncio
async def test_input_keys_scopes_tool_inputs(app: AppContext) -> None:
    """Only specified input_keys are passed to tools."""
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Scoped Inputs",
        config={"topic": "weather", "tools": ["weather_lookup"], "input_keys": ["location"]},
    )
    app.tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="Sunny",
            artifact_handle=None,
            truncated=False,
        )
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"findings": ["Sunny"], "recommendations": [], "sources": []}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    executor = InvestigateNode()
    inputs = {"location": "NYC", "extra": "ignored"}
    result = await executor.execute(app, node, inputs)

    assert result["findings"] == ["Sunny"]
    app.tool_registry.call.assert_awaited_once_with("weather_lookup", {"location": "NYC"})


@pytest.mark.asyncio
async def test_empty_input_keys_passes_first_predecessor(app: AppContext) -> None:
    """Empty input_keys passes only the first predecessor's output."""
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="First Only",
        config={"topic": "summary", "tools": ["summarizer"]},
    )
    app.tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="Short",
            artifact_handle=None,
            truncated=False,
        )
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"findings": ["Short"], "recommendations": [], "sources": []}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    executor = InvestigateNode()
    inputs = {"first": "data", "second": "more"}
    await executor.execute(app, node, inputs)

    app.tool_registry.call.assert_awaited_once_with("summarizer", {"first": "data"})


@pytest.mark.asyncio
async def test_input_keys_missing_key_logs_warning(
    app: AppContext, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing input_keys reference logs a warning."""
    node = WorkflowNode(
        id="n1",
        type="investigate",
        label="Missing Key",
        config={"topic": "test", "tools": ["tool1"], "input_keys": ["missing"]},
    )
    app.tool_registry.call = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="ok",
            artifact_handle=None,
            truncated=False,
        )
    )
    app.inference.chat = AsyncMock(
        return_value=ChatResponse(
            content='{"findings": ["ok"], "recommendations": [], "sources": []}',
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
    )

    executor = InvestigateNode()
    with caplog.at_level("WARNING"):
        await executor.execute(app, node, {})

    assert "missing key" in caplog.text.lower()
