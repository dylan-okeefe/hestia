"""Tests for concurrent tool dispatch in the orchestrator (L40)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature, ToolCall
from hestia.orchestrator.engine import Orchestrator
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolRegistry
from hestia.tools.types import ToolCallResult


def _make_session() -> Session:
    from datetime import datetime

    return Session(
        id="test-session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


def _make_orchestrator() -> Orchestrator:
    mock_inference = MagicMock()
    mock_session_store = MagicMock()
    mock_context_builder = MagicMock()
    mock_tool_registry = ToolRegistry(MagicMock())
    mock_policy = MagicMock()

    mock_policy.filter_tools.return_value = None
    mock_policy.reasoning_budget.return_value = 2048

    mock_session_store.insert_turn = AsyncMock()
    mock_session_store.update_turn = AsyncMock()
    mock_session_store.append_transition = AsyncMock()
    mock_session_store.append_message = AsyncMock()
    mock_session_store.get_messages = AsyncMock(return_value=[])

    return Orchestrator(
        inference=mock_inference,
        session_store=mock_session_store,
        context_builder=mock_context_builder,
        tool_registry=mock_tool_registry,
        policy=mock_policy,
        confirm_callback=None,
    )


@pytest.mark.asyncio
async def test_concurrent_tools_run_in_parallel():
    """Three concurrent tools should complete in ~0.3 s, not ~0.9 s."""
    orchestrator = _make_orchestrator()
    registry = orchestrator._tools

    sleep_time = 0.3

    async def slow_tool(**kwargs: object) -> str:
        await asyncio.sleep(sleep_time)
        return "done"

    # Register three slow tools as concurrent (default)
    for name in ("slow_a", "slow_b", "slow_c"):
        registry._tools[name] = ToolMetadata(
            name=name,
            public_description="slow",
            internal_description="",
            parameters_schema={},
            requires_confirmation=False,
            ordering="concurrent",
            handler=slow_tool,
        )

    tool_calls = [
        ToolCall(id="tc1", name="slow_a", arguments={}),
        ToolCall(id="tc2", name="slow_b", arguments={}),
        ToolCall(id="tc3", name="slow_c", arguments={}),
    ]

    start = asyncio.get_event_loop().time()
    messages, handles = await orchestrator._execute_tool_calls(
        _make_session(), tool_calls
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(messages) == 3
    assert all(m.role == "tool" for m in messages)
    # Emission order preserved
    assert messages[0].tool_call_id == "tc1"
    assert messages[1].tool_call_id == "tc2"
    assert messages[2].tool_call_id == "tc3"
    # Parallelism: should be < 0.7 s for 3×0.3 s tools
    assert elapsed < 0.7


@pytest.mark.asyncio
async def test_serial_tools_run_sequentially():
    """A tool marked ordering='serial' forces sequential dispatch."""
    orchestrator = _make_orchestrator()
    registry = orchestrator._tools

    sleep_time = 0.3

    async def slow_tool(**kwargs: object) -> str:
        await asyncio.sleep(sleep_time)
        return "done"

    registry._tools["slow_a"] = ToolMetadata(
        name="slow_a",
        public_description="slow",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=slow_tool,
    )
    registry._tools["slow_b"] = ToolMetadata(
        name="slow_b",
        public_description="slow",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="serial",
        handler=slow_tool,
    )

    tool_calls = [
        ToolCall(id="tc1", name="slow_a", arguments={}),
        ToolCall(id="tc2", name="slow_b", arguments={}),
    ]

    start = asyncio.get_event_loop().time()
    messages, handles = await orchestrator._execute_tool_calls(
        _make_session(), tool_calls
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(messages) == 2
    # serial tool forces sequential → elapsed > 0.5 s
    assert elapsed > 0.5


@pytest.mark.asyncio
async def test_confirmation_tool_runs_serially():
    """A tool with requires_confirmation=True runs serially even if others are concurrent."""
    orchestrator = _make_orchestrator()
    registry = orchestrator._tools

    sleep_time = 0.3

    async def slow_tool(**kwargs: object) -> str:
        await asyncio.sleep(sleep_time)
        return "done"

    registry._tools["safe"] = ToolMetadata(
        name="safe",
        public_description="slow",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=slow_tool,
    )
    registry._tools["danger"] = ToolMetadata(
        name="danger",
        public_description="slow",
        internal_description="",
        parameters_schema={},
        requires_confirmation=True,
        ordering="concurrent",
        handler=slow_tool,
    )

    tool_calls = [
        ToolCall(id="tc1", name="safe", arguments={}),
        ToolCall(id="tc2", name="danger", arguments={}),
    ]

    start = asyncio.get_event_loop().time()
    messages, handles = await orchestrator._execute_tool_calls(
        _make_session(), tool_calls
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(messages) == 2
    # danger is serial → total > 0.5 s
    assert elapsed > 0.5
