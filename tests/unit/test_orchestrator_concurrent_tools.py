"""Tests for concurrent tool dispatch in the orchestrator (L40)."""

import asyncio
from unittest.mock import MagicMock

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature, ToolCall
from hestia.orchestrator.execution import TurnExecution
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolRegistry


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


def _make_turn_execution(registry: ToolRegistry | None = None) -> TurnExecution:
    return TurnExecution(
        tool_registry=registry or ToolRegistry(MagicMock()),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        confirm_callback=None,
    )


@pytest.mark.asyncio
async def test_concurrent_tools_run_in_parallel():
    """Three concurrent tools should complete in ~0.3 s, not ~0.9 s."""
    turn_execution = _make_turn_execution()
    registry = turn_execution._tools

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
    messages, handles = await turn_execution._execute_tool_calls(
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
    turn_execution = _make_turn_execution()
    registry = turn_execution._tools

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
    messages, handles = await turn_execution._execute_tool_calls(
        _make_session(), tool_calls
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(messages) == 2
    # serial tool forces sequential → elapsed > 0.5 s
    assert elapsed > 0.5


@pytest.mark.asyncio
async def test_confirmation_tool_runs_serially():
    """A tool with requires_confirmation=True runs serially even if others are concurrent."""
    turn_execution = _make_turn_execution()
    registry = turn_execution._tools

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
    messages, handles = await turn_execution._execute_tool_calls(
        _make_session(), tool_calls
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(messages) == 2
    # danger is serial → total > 0.5 s
    assert elapsed > 0.5


@pytest.mark.asyncio
async def test_concurrent_tool_exception_does_not_kill_siblings():
    """M3: an exception in one concurrent tool is captured; siblings complete."""
    turn_execution = _make_turn_execution()
    registry = turn_execution._tools

    async def ok_tool(**kwargs: object) -> str:
        await asyncio.sleep(0.1)
        return "ok"

    async def boom_tool(**kwargs: object) -> str:
        await asyncio.sleep(0.05)
        raise RuntimeError("intentional failure")

    registry._tools["ok_a"] = ToolMetadata(
        name="ok_a",
        public_description="ok",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=ok_tool,
    )
    registry._tools["boom"] = ToolMetadata(
        name="boom",
        public_description="boom",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=boom_tool,
    )
    registry._tools["ok_b"] = ToolMetadata(
        name="ok_b",
        public_description="ok",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=ok_tool,
    )

    tool_calls = [
        ToolCall(id="tc1", name="ok_a", arguments={}),
        ToolCall(id="tc2", name="boom", arguments={}),
        ToolCall(id="tc3", name="ok_b", arguments={}),
    ]

    messages, handles = await turn_execution._execute_tool_calls(
        _make_session(), tool_calls
    )

    assert len(messages) == 3
    # ok_a and ok_b succeeded
    assert messages[0].content == "ok"
    assert messages[2].content == "ok"
    # boom errored gracefully
    assert messages[1].role == "tool"
    assert "intentional failure" in messages[1].content
