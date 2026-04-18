"""Lock the contract that TurnState and ToolResult live in orchestrator/types.py only."""

import hestia.core.types as core_types


def test_turnstate_not_in_core_types():
    assert not hasattr(core_types, "TurnState")
    assert not hasattr(core_types, "TERMINAL_STATES")


def test_toolresult_not_in_core_types():
    assert not hasattr(core_types, "ToolResult")


def test_orchestrator_turnstate_still_exists():
    from hestia.orchestrator.types import TurnState  # noqa: F401
