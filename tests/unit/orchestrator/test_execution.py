"""Unit tests for TurnExecution direct tool dispatch (L161)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature, ToolCall
from hestia.orchestrator.execution import TurnExecution
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolRegistry


def _make_session() -> Session:
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


@pytest.mark.asyncio
async def test_direct_write_file_dispatch():
    """A direct write_file tool call is dispatched correctly."""
    registry = ToolRegistry(MagicMock())
    async def _write_file(**kwargs: object) -> str:
        return "Wrote file"

    registry._tools["write_file"] = ToolMetadata(
        name="write_file",
        public_description="Write a file",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=_write_file,
    )

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    tc = ToolCall(
        id="tc1", name="write_file", arguments={"path": "/tmp/test.txt", "content": "hi"}
    )
    result = await execution._dispatch_tool_call(_make_session(), tc)
    assert result.status == "ok"
    assert "Wrote file" in result.content


def test_call_tool_not_in_dispatch_table():
    """call_tool is no longer in the meta-tool dispatch table."""
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )
    # The _meta_tools attribute was removed entirely in L161.
    assert not hasattr(execution, "_meta_tools")
