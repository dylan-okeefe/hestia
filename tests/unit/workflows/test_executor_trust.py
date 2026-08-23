"""Workflow executor tests for the L222 capability gate integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from hestia.app import AppContext
from hestia.config import HestiaConfig
from hestia.persistence.db import Database
from hestia.policy.gate import CapabilityGate, CapabilityRequest, CapabilityResult
from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolRegistry
from hestia.tools.types import ToolCallResult
from hestia.workflows.executor import WorkflowExecutor
from hestia.workflows.models import Workflow, WorkflowNode, WorkflowVersion
from hestia.workflows.store import WorkflowStore


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[Database, None]:
    """Create an in-memory database for testing."""
    database = Database(url="sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def workflow_store(db: Database) -> WorkflowStore:
    """Create a WorkflowStore for testing."""
    store = WorkflowStore(db)
    await store.create_tables()
    return store


@pytest.fixture
def app(tmp_path: Path, db: Database) -> AppContext:
    """Create a minimal AppContext with mocked inference and tool registry."""
    cfg = HestiaConfig.default()
    cfg.inference.model_name = "dummy"
    cfg.storage.database_url = "sqlite+aiosqlite:///:memory:"
    cfg.storage.artifacts_dir = tmp_path / "artifacts"
    app = AppContext(cfg)
    app.db = db
    app.inference = AsyncMock()
    app.tool_registry = MagicMock(spec=ToolRegistry)
    return app


@pytest.fixture
def gated_app(app: AppContext) -> AppContext:
    """Return an app whose tool registry and capability gate agree on tool labels.

    The registry describes ``terminal`` as a destructive shell tool and
    ``current_time`` as a safe tool.  Calls return a minimal success result.
    """
    reg: Any = MagicMock(spec=ToolRegistry)

    def _describe(name: str) -> ToolMetadata:
        if name == "terminal":
            return ToolMetadata(
                name="terminal",
                public_description="Run a shell command",
                internal_description="",
                parameters_schema={"type": "object", "properties": {}},
                capabilities=[SHELL_EXEC],
            )
        if name == "browser_login":
            return ToolMetadata(
                name="browser_login",
                public_description="Browser login",
                internal_description="",
                parameters_schema={"type": "object", "properties": {}},
                capabilities=[],
            )
        return ToolMetadata(
            name=name,
            public_description=f"Tool {name}",
            internal_description="",
            parameters_schema={"type": "object", "properties": {}},
            capabilities=[],
        )

    reg.describe.side_effect = _describe
    call_mock = AsyncMock(
        return_value=ToolCallResult(
            status="ok",
            content="done",
            artifact_handle=None,
            truncated=False,
        )
    )
    reg.call = call_mock
    app.tool_registry = reg
    app.capability_gate = CapabilityGate(
        config=app.config,
        user_store=app.user_store,
        registry=reg,
        event_store=None,
    )
    return app


@pytest.mark.asyncio
async def test_workflow_blocks_destructive_without_allow_list(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """Destructive tool nodes fail when the workflow has no allow-list."""
    wf = Workflow(id="wf_unsafe", name="Unsafe", trust_level="paranoid")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_unsafe",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="terminal",
                label="Run Shell",
                capabilities=[SHELL_EXEC],
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_unsafe", {})

    error = result.node_results[0].error or ""
    assert result.status == "failed"
    assert result.node_results[0].node_id == "n1"
    assert "[CATEGORY: BLOCKED]" in error
    assert "Capability gate denied" in error
    call_mock = cast(AsyncMock, gated_app.tool_registry.call)
    call_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_allows_destructive_when_allow_listed(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """Destructive tool nodes succeed when explicitly allow-listed."""
    wf = Workflow(
        id="wf_allowed",
        name="Allowed",
        trust_level="paranoid",
        allow_listed_tools={"terminal"},
    )
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_allowed",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="terminal",
                label="Run Shell",
                capabilities=[SHELL_EXEC],
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_allowed", {})

    assert result.status == "ok"
    assert result.node_results[0].status == "ok"
    call_mock = cast(AsyncMock, gated_app.tool_registry.call)
    call_mock.assert_awaited_once_with("terminal", {"data": {}})


@pytest.mark.asyncio
async def test_workflow_allows_safe_tool_without_allow_list(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """Non-destructive tool nodes do not require an allow-list."""
    wf = Workflow(id="wf_safe", name="Safe", trust_level="paranoid")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_safe",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="current_time",
                label="Time",
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_safe", {})

    assert result.status == "ok"
    assert result.node_results[0].status == "ok"
    call_mock = cast(AsyncMock, gated_app.tool_registry.call)
    call_mock.assert_awaited_once_with("current_time", {"data": {}})


@pytest.mark.asyncio
async def test_workflow_blocks_hardcoded_destructive_tool_name(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """``browser_login`` is treated as destructive even with empty capabilities."""
    wf = Workflow(id="wf_browser", name="Browser", trust_level="paranoid")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_browser",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="browser_login",
                label="Login",
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_browser", {})

    error = result.node_results[0].error or ""
    assert result.status == "failed"
    assert result.node_results[0].node_id == "n1"
    assert "[CATEGORY: BLOCKED]" in error
    call_mock = cast(AsyncMock, gated_app.tool_registry.call)
    call_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_allow_list_passed_to_gate(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """The executor passes ``workflow.allow_listed_tools`` to the gate."""
    wf = Workflow(
        id="wf_audit",
        name="Audit",
        trust_level="paranoid",
        allow_listed_tools={"terminal"},
    )
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_audit",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="terminal",
                label="Run Shell",
                capabilities=[SHELL_EXEC],
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    original_check = gated_app.capability_gate.check

    async def _checked(request: CapabilityRequest, **kwargs: Any) -> CapabilityResult:
        return await original_check(request, **kwargs)

    executor = WorkflowExecutor(gated_app)
    with patch.object(gated_app.capability_gate, "check", AsyncMock(side_effect=_checked)) as check_mock:
        await executor.execute("wf_audit", {})

    call_args = check_mock.call_args
    assert call_args is not None
    assert call_args.kwargs.get("allow_list") == {"terminal"}


@pytest.mark.asyncio
async def test_tool_call_node_is_gated(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """SEC-001: a tool_call node invoking a destructive tool must be denied.

    The old NODE_TYPES dispatch returned before reaching the gate block, so
    {'type': 'tool_call', 'config': {'tool_name': 'terminal'}} executed shell
    commands unattended.
    """
    wf = Workflow(id="wf_tc_gate", name="TC Gate", trust_level="paranoid")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_tc_gate",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="tool_call",
                label="Run Shell",
                config={"tool_name": "terminal", "command": "echo hi"},
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_tc_gate", {})

    assert result.status == "failed"
    error = result.node_results[0].error or ""
    assert "BLOCKED" in error
    gated_app.tool_registry.call.assert_not_called()


@pytest.mark.asyncio
async def test_investigate_node_tools_are_gated(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """SEC-001: investigate nodes gate every configured tool."""
    wf = Workflow(id="wf_inv_gate", name="Inv Gate", trust_level="paranoid")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_inv_gate",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="investigate",
                label="Investigate",
                config={"topic": "x", "tools": ["terminal"]},
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_inv_gate", {})

    assert result.status == "failed"
    assert "BLOCKED" in (result.node_results[0].error or "")
    gated_app.tool_registry.call.assert_not_called()


@pytest.mark.asyncio
async def test_tool_call_node_allowed_via_allow_list(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """A workflow's allow_listed_tools permits explicitly listed tools through
    the tool_call node path."""
    wf = Workflow(
        id="wf_tc_ok",
        name="TC Allowed",
        trust_level="household",
        allow_listed_tools={"current_time"},
    )
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_tc_ok",
        version=1,
        nodes=[
            WorkflowNode(
                id="n1",
                type="tool_call",
                label="Time",
                config={"tool_name": "current_time"},
            )
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_tc_ok", {})

    assert result.status == "ok"
    gated_app.tool_registry.call.assert_awaited_once()


@pytest.mark.asyncio
async def test_investigate_tools_via_inputs_are_gated(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """Review defect 1: 'tools' arriving through interpolated inputs (not
    config) must still pass the gate."""
    wf = Workflow(id="wf_inv_inputs", name="Inv Inputs", trust_level="paranoid")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_inv_inputs",
        version=1,
        nodes=[
            WorkflowNode(id="n1", type="investigate", label="Investigate", config={"topic": "x"})
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_inv_inputs", {"tools": ["terminal"]})

    assert result.status == "failed"
    gated_app.tool_registry.call.assert_not_called()


@pytest.mark.asyncio
async def test_dict_shaped_tools_fail_closed(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    """Review defect 1: a dict-shaped tools value must be denied outright.

    The previous gate duplicate handled only str/list, so
    {'terminal': True} gated nothing and then executed its keys.
    """
    wf = Workflow(id="wf_dict", name="Dict Tools", trust_level="household")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_dict",
        version=1,
        nodes=[
            WorkflowNode(id="n1", type="investigate", label="Investigate", config={"topic": "x"})
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_dict", {"tools": {"terminal": True}})

    assert result.status == "failed"
    error = result.node_results[0].error or ""
    assert "BLOCKED" in error or "refusing to execute" in error
    gated_app.tool_registry.call.assert_not_called()


@pytest.mark.asyncio
async def test_non_string_tool_list_entries_fail_closed(
    workflow_store: WorkflowStore,
    gated_app: AppContext,
) -> None:
    wf = Workflow(id="wf_ints", name="Int Tools", trust_level="household")
    await workflow_store.save_workflow(wf)

    version = WorkflowVersion(
        workflow_id="wf_ints",
        version=1,
        nodes=[
            WorkflowNode(id="n1", type="investigate", label="Investigate", config={"topic": "x"})
        ],
        edges=[],
        is_active=True,
    )
    await workflow_store.save_version(version)

    executor = WorkflowExecutor(gated_app)
    result = await executor.execute("wf_ints", {"tools": [123]})

    assert result.status == "failed"
    gated_app.tool_registry.call.assert_not_called()
