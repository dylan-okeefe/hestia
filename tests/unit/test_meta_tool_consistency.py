"""D5: meta-tool names agree across schema list, guard set, dispatch table."""

from __future__ import annotations

from unittest.mock import MagicMock

from hestia.orchestrator import execution as execution_module
from hestia.orchestrator.execution import TurnExecution
from hestia.tools.registry import ToolRegistry


def test_meta_tool_names_agree_across_schema_guard_and_dispatch() -> None:
    reg = ToolRegistry.__new__(ToolRegistry)
    schema_names = {s.function.name for s in ToolRegistry.meta_tool_schemas(reg)}

    te = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )
    dispatch_names = set(te._meta_tools.keys())
    guard_names = set(execution_module._META_TOOL_CHAIN_NAMES)

    assert schema_names == dispatch_names == guard_names, (
        f"meta-tool drift: schemas={schema_names} dispatch={dispatch_names} "
        f"guard={guard_names}"
    )
