"""Unit tests for WorkflowExecutor."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from hestia.app import AppContext
from hestia.config import HestiaConfig
from hestia.core.types import ChatResponse, Message
from hestia.persistence.db import Database
from hestia.tools.capabilities import SHELL_EXEC, WRITE_LOCAL
from hestia.tools.registry import ToolRegistry
from hestia.tools.types import ToolCallResult
from hestia.workflows.executor import ExecutionResult, WorkflowExecutor
from hestia.workflows.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowVersion
from hestia.workflows.store import WorkflowStore


@pytest_asyncio.fixture
async def db() -> Database:
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
def app(tmp_path, db: Database) -> AppContext:
    """Create a minimal AppContext with mocked inference and tool registry."""
    cfg = HestiaConfig.default()
    cfg.storage.database_url = "sqlite+aiosqlite:///:memory:"
    cfg.storage.artifacts_dir = tmp_path / "artifacts"
    app = AppContext(cfg)
    app.db = db
    app.inference = AsyncMock()  # type: ignore[method-assign]
    app.tool_registry = MagicMock(spec=ToolRegistry)  # type: ignore[method-assign]
    return app


@pytest_asyncio.fixture
async def executor(app: AppContext) -> WorkflowExecutor:
    """Create a WorkflowExecutor for testing."""
    return WorkflowExecutor(app)


class TestExecuteHappyPath:
    """Tests for successful workflow execution."""

    @pytest.mark.asyncio
    async def test_single_node_workflow(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """A workflow with one node executes successfully."""
        wf = Workflow(id="wf_1", name="Single Node", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(id="n1", type="echo", label="Echo")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.tool_registry.call = AsyncMock(return_value=ToolCallResult(
            status="ok",
            content="hello",
            artifact_handle=None,
            truncated=False,
        ))

        result = await executor.execute("wf_1", {"text": "hi"})

        assert isinstance(result, ExecutionResult)
        assert result.status == "ok"
        assert len(result.node_results) == 1
        assert result.node_results[0].node_id == "n1"
        assert result.node_results[0].status == "ok"
        assert result.node_results[0].output == "hello"
        assert result.outputs["trigger"] == {"text": "hi"}
        assert result.outputs["n1"] == "hello"

    @pytest.mark.asyncio
    async def test_two_node_chain(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """Nodes execute in topological order with input resolution."""
        wf = Workflow(id="wf_1", name="Chain", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node1 = WorkflowNode(id="n1", type="upper", label="Upper")
        node2 = WorkflowNode(id="n2", type="append", label="Append")
        edge = WorkflowEdge(
            id="e1",
            source_node_id="n1",
            target_node_id="n2",
            target_handle="input",
        )
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node1, node2],
            edges=[edge],
            is_active=True,
        )
        await workflow_store.save_version(version)

        async def tool_call(name: str, args: dict[str, Any]) -> ToolCallResult:
            if name == "upper":
                return ToolCallResult(
                    status="ok",
                    content=args.get("text", "").upper(),
                    artifact_handle=None,
                    truncated=False,
                )
            if name == "append":
                return ToolCallResult(
                    status="ok",
                    content=args.get("input", "") + "!",
                    artifact_handle=None,
                    truncated=False,
                )
            return ToolCallResult(status="ok", content="", artifact_handle=None, truncated=False)

        app.tool_registry.call = AsyncMock(side_effect=tool_call)

        result = await executor.execute("wf_1", {"text": "hello"})

        assert result.status == "ok"
        assert len(result.node_results) == 2
        assert result.outputs["n1"] == "HELLO"
        assert result.outputs["n2"] == "HELLO!"

    @pytest.mark.asyncio
    async def test_inference_node(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """An inference node delegates to the inference client."""
        wf = Workflow(id="wf_1", name="Inference", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(id="n1", type="inference", label="Ask")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.inference.chat = AsyncMock(return_value=ChatResponse(
            content="42",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        ))

        result = await executor.execute("wf_1", {"question": "meaning of life"})

        assert result.status == "ok"
        assert result.outputs["n1"] == "42"
        app.inference.chat.assert_awaited_once()
        call_args = app.inference.chat.await_args
        assert call_args is not None
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        assert isinstance(messages[0], Message)
        assert messages[0].content == "{'question': 'meaning of life'}"


class TestTrustEnforcement:
    """Tests for trust ladder enforcement."""

    @pytest.mark.asyncio
    async def test_paranoid_blocks_shell_exec(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
    ) -> None:
        """Paranoid trust level blocks shell_exec capability."""
        wf = Workflow(id="wf_1", name="Unsafe", trust_level="paranoid")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(
            id="n1",
            type="terminal",
            label="Run Shell",
            capabilities=[SHELL_EXEC],
        )
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        result = await executor.execute("wf_1", {})

        assert result.status == "failed"
        assert result.node_results[0].node_id == "n1"
        assert "denies capabilities" in result.node_results[0].error

    @pytest.mark.asyncio
    async def test_household_allows_write_local(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """Household trust level allows write_local but blocks shell_exec."""
        wf = Workflow(id="wf_1", name="Mixed", trust_level="household")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(
            id="n1",
            type="write_file",
            label="Write",
            capabilities=[WRITE_LOCAL],
        )
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.tool_registry.call = AsyncMock(return_value=ToolCallResult(
            status="ok",
            content="done",
            artifact_handle=None,
            truncated=False,
        ))

        result = await executor.execute("wf_1", {})

        assert result.status == "ok"
        assert result.outputs["n1"] == "done"

    @pytest.mark.asyncio
    async def test_developer_allows_all(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """Developer trust level allows all capabilities."""
        wf = Workflow(id="wf_1", name="Dev", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(
            id="n1",
            type="terminal",
            label="Run Shell",
            capabilities=[SHELL_EXEC, WRITE_LOCAL],
        )
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.tool_registry.call = AsyncMock(return_value=ToolCallResult(
            status="ok",
            content="ok",
            artifact_handle=None,
            truncated=False,
        ))

        result = await executor.execute("wf_1", {})

        assert result.status == "ok"


class TestFailFast:
    """Tests for fail-fast behavior."""

    @pytest.mark.asyncio
    async def test_node_failure_stops_execution(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """If a node fails, subsequent nodes are not executed."""
        wf = Workflow(id="wf_1", name="Fail Fast", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node1 = WorkflowNode(id="n1", type="bad", label="Bad")
        node2 = WorkflowNode(id="n2", type="good", label="Good")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node1, node2],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.tool_registry.call = AsyncMock(side_effect=RuntimeError("boom"))

        result = await executor.execute("wf_1", {})

        assert result.status == "failed"
        assert len(result.node_results) == 1
        assert result.node_results[0].node_id == "n1"
        assert "boom" in result.node_results[0].error
        assert "n2" not in result.outputs


class TestCostTracking:
    """Tests for execution cost and timing tracking."""

    @pytest.mark.asyncio
    async def test_inference_node_tracks_tokens(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """An inference node records prompt and completion tokens."""
        wf = Workflow(id="wf_1", name="Inference", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(id="n1", type="inference", label="Ask")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.inference.chat = AsyncMock(return_value=ChatResponse(
            content="42",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        ))

        result = await executor.execute("wf_1", {"question": "meaning of life"})

        assert result.status == "ok"
        assert result.total_prompt_tokens == 100
        assert result.total_completion_tokens == 50
        assert result.total_elapsed_ms >= 0
        nr = result.node_results[0]
        assert nr.prompt_tokens == 100
        assert nr.completion_tokens == 50
        assert nr.elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_llm_decision_node_tracks_tokens(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """An llm_decision node records prompt and completion tokens."""
        wf = Workflow(id="wf_1", name="Decision", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(id="n1", type="llm_decision", label="Decide", config={"branches": ["a", "b"]})
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.inference.chat = AsyncMock(return_value=ChatResponse(
            content="a",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
        ))

        result = await executor.execute("wf_1", {})

        assert result.status == "ok"
        assert result.total_prompt_tokens == 80
        assert result.total_completion_tokens == 20
        nr = result.node_results[0]
        assert nr.prompt_tokens == 80
        assert nr.completion_tokens == 20
        assert nr.output == "a"

    @pytest.mark.asyncio
    async def test_multiple_nodes_aggregate_tokens(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """Token usage is summed across multiple inference nodes."""
        wf = Workflow(id="wf_1", name="Multi", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node1 = WorkflowNode(id="n1", type="inference", label="First")
        node2 = WorkflowNode(id="n2", type="inference", label="Second")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node1, node2],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.inference.chat = AsyncMock(side_effect=[
            ChatResponse(
                content="one",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            ChatResponse(
                content="two",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
            ),
        ])

        result = await executor.execute("wf_1", {})

        assert result.status == "ok"
        assert result.total_prompt_tokens == 30
        assert result.total_completion_tokens == 15

    @pytest.mark.asyncio
    async def test_failed_node_records_elapsed_ms(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """A failed node still records elapsed time."""
        wf = Workflow(id="wf_1", name="Fail", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node = WorkflowNode(id="n1", type="bad", label="Bad")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node],
            edges=[],
            is_active=True,
        )
        await workflow_store.save_version(version)

        app.tool_registry.call = AsyncMock(side_effect=RuntimeError("boom"))

        result = await executor.execute("wf_1", {})

        assert result.status == "failed"
        assert result.node_results[0].elapsed_ms >= 0
        assert result.total_elapsed_ms >= 0


class TestEdgeCases:
    """Tests for edge cases and errors."""

    @pytest.mark.asyncio
    async def test_workflow_not_found(
        self,
        executor: WorkflowExecutor,
    ) -> None:
        """Executing a non-existent workflow returns a failed result."""
        result = await executor.execute("missing", {})

        assert result.status == "failed"
        assert "not found" in result.node_results[0].error

    @pytest.mark.asyncio
    async def test_no_active_version(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
    ) -> None:
        """Executing a workflow with no active version returns a failed result."""
        wf = Workflow(id="wf_1", name="No Version")
        await workflow_store.save_workflow(wf)

        result = await executor.execute("wf_1", {})

        assert result.status == "failed"
        assert "No active version" in result.node_results[0].error

    @pytest.mark.asyncio
    async def test_cyclic_graph(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
    ) -> None:
        """A cyclic workflow graph returns a failed result."""
        wf = Workflow(id="wf_1", name="Cycle", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node1 = WorkflowNode(id="n1", type="a", label="A")
        node2 = WorkflowNode(id="n2", type="b", label="B")
        edge1 = WorkflowEdge(id="e1", source_node_id="n1", target_node_id="n2")
        edge2 = WorkflowEdge(id="e2", source_node_id="n2", target_node_id="n1")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node1, node2],
            edges=[edge1, edge2],
            is_active=True,
        )
        await workflow_store.save_version(version)

        result = await executor.execute("wf_1", {})

        assert result.status == "failed"
        assert "cycle" in result.node_results[0].error.lower()

    @pytest.mark.asyncio
    async def test_topological_order_respected(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        app: AppContext,
    ) -> None:
        """Nodes with dependencies execute after their dependencies."""
        wf = Workflow(id="wf_1", name="Order", trust_level="developer")
        await workflow_store.save_workflow(wf)

        node_a = WorkflowNode(id="a", type="tool", label="A")
        node_b = WorkflowNode(id="b", type="tool", label="B")
        node_c = WorkflowNode(id="c", type="tool", label="C")
        edge_ab = WorkflowEdge(id="e1", source_node_id="a", target_node_id="b")
        edge_bc = WorkflowEdge(id="e2", source_node_id="b", target_node_id="c")
        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[node_a, node_b, node_c],
            edges=[edge_ab, edge_bc],
            is_active=True,
        )
        await workflow_store.save_version(version)

        call_order: list[str] = []

        async def track_call(name: str, _args: dict[str, Any]) -> ToolCallResult:
            call_order.append(name)
            return ToolCallResult(status="ok", content="ok", artifact_handle=None, truncated=False)

        app.tool_registry.call = AsyncMock(side_effect=track_call)

        result = await executor.execute("wf_1", {})

        assert result.status == "ok"
        assert call_order == ["tool", "tool", "tool"]
        # Verify outputs were set in dependency order
        ids = [nr.node_id for nr in result.node_results]
        assert ids == ["a", "b", "c"]
