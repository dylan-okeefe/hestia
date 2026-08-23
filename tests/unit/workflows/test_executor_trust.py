"""Workflow executor tests for the L222 capability gate integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from hestia.app import AppContext
from hestia.config import HestiaConfig
from hestia.persistence.db import Database
from hestia.policy.gate import CapabilityGate, CapabilityRequest, CapabilityResult
from hestia.tools.capabilities import SHELL_EXEC
from hestia.tools.registry import ToolRegistry
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
    # A REAL registry with stub tools registered through the @tool decorator,
    # bound to a REAL gate. This exercises the L245 chokepoint itself: the
    # enforcement lives inside ToolRegistry.call, not in executor pre-checks.
    reg = ToolRegistry(artifact_store=MagicMock())

    def _stub(name: str, caps: list[str]):
        from hestia.tools.metadata import tool as _tool

        @_tool(
            name=name,
            public_description=f"Stub {name}",
            internal_description="",
            parameters_schema={"type": "object", "properties": {}},
            max_inline_chars=4000,
            tags=[],
            capabilities=caps,
        )
        async def _handler(**kwargs: Any) -> str:
            calls.append((name, kwargs))
            return f"{name} ok"

        return _handler

    calls: list[tuple[str, dict[str, Any]]] = []
    reg.register(_stub("terminal", [SHELL_EXEC]))
    reg.register(_stub("browser_login", []))
    reg.register(_stub("current_time", []))
    reg.calls = calls  # type: ignore[attr-defined]  # test observation hook

    app.tool_registry = reg
    app.capability_gate = CapabilityGate(
        config=app.config,
        user_store=app.user_store,
        registry=reg,
        event_store=None,
    )
    # L245: production binds the gate into the registry; tests mirror that.
    reg.bind_gate(app.capability_gate)
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
    # Real registry recorded nothing: the chokepoint denied before dispatch.
    assert gated_app.tool_registry._artifact_store  # registry is real
    assert not any(
        name == "terminal" for name, _kw in gated_app.tool_registry.calls
    )


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
    assert ("terminal", {"data": {}}) in gated_app.tool_registry.calls


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
    assert ("current_time", {"data": {}}) in gated_app.tool_registry.calls


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
    # Real registry recorded nothing: the chokepoint denied before dispatch.
    assert gated_app.tool_registry._artifact_store  # registry is real
    assert not any(
        name == "terminal" for name, _kw in gated_app.tool_registry.calls
    )


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
    assert gated_app.tool_registry._tools  # real registry in place


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
    assert gated_app.tool_registry._tools  # real registry in place


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
    assert ("current_time", {}) in gated_app.tool_registry.calls


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
    assert gated_app.tool_registry._tools  # real registry in place


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
    assert gated_app.tool_registry._tools  # real registry in place


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
    assert gated_app.tool_registry._tools  # real registry in place
