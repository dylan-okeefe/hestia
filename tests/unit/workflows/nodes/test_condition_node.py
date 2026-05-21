"""Tests for ConditionNode."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from hestia.app import AppContext
from hestia.workflows.models import WorkflowNode
from hestia.workflows.nodes.condition import ConditionNode


@pytest.fixture
def app() -> AppContext:
    return MagicMock(spec=AppContext)  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_simple_comparison(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "value > 10"},
    )
    executor = ConditionNode()
    assert await executor.execute(app, node, {"value": 15}) is True
    assert await executor.execute(app, node, {"value": 5}) is False


@pytest.mark.asyncio
async def test_equality(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "status == 'ok'"},
    )
    executor = ConditionNode()
    assert await executor.execute(app, node, {"status": "ok"}) is True
    assert await executor.execute(app, node, {"status": "fail"}) is False


@pytest.mark.asyncio
async def test_logical_and(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "a > 1 and b < 5"},
    )
    executor = ConditionNode()
    assert await executor.execute(app, node, {"a": 2, "b": 3}) is True
    assert await executor.execute(app, node, {"a": 0, "b": 3}) is False


@pytest.mark.asyncio
async def test_in_operator(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "name in allowed"},
    )
    executor = ConditionNode()
    assert (
        await executor.execute(
            app, node, {"name": "alice", "allowed": ["alice", "bob"]}
        )
        is True
    )
    assert (
        await executor.execute(
            app, node, {"name": "charlie", "allowed": ["alice", "bob"]}
        )
        is False
    )


@pytest.mark.asyncio
async def test_missing_expression_raises(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={},
    )
    executor = ConditionNode()
    with pytest.raises(ValueError, match="expression"):
        await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_unsafe_expression_blocked(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "__import__('os').system('ls')"},
    )
    executor = ConditionNode()
    with pytest.raises(ValueError, match="Unsupported"):
        await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_private_attribute_access_blocked(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "x.__class__"},
    )
    executor = ConditionNode()
    with pytest.raises(ValueError, match="private attribute"):
        await executor.execute(app, node, {"x": 42})


@pytest.mark.asyncio
async def test_pow_operator_blocked(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "2 ** 100"},
    )
    executor = ConditionNode()
    with pytest.raises(ValueError, match="Unsupported binary operator"):
        await executor.execute(app, node, {})


@pytest.mark.asyncio
async def test_datetime_input_json_normalized(app: AppContext) -> None:
    node = WorkflowNode(
        id="n1",
        type="condition",
        label="Check",
        config={"expression": "ts == '2024-01-01 12:00:00'"},
    )
    executor = ConditionNode()
    dt = datetime(2024, 1, 1, 12, 0, 0)
    result = await executor.execute(app, node, {"ts": dt})
    assert result is True
