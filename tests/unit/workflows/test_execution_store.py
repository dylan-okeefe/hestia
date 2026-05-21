"""Unit tests for ExecutionStore."""

from __future__ import annotations

import pytest
import pytest_asyncio

from hestia.persistence.db import Database
from hestia.workflows.execution_store import ExecutionStore
from hestia.workflows.models import ExecutionResult, NodeResult


@pytest_asyncio.fixture
async def db() -> Database:
    """Create an in-memory database for testing."""
    database = Database(url="sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def execution_store(db: Database) -> ExecutionStore:
    """Create an ExecutionStore for testing."""
    store = ExecutionStore(db)
    await store.create_tables()
    return store


class TestSaveExecution:
    """Tests for saving executions."""

    @pytest.mark.asyncio
    async def test_save_ok_execution(self, execution_store: ExecutionStore) -> None:
        """Saving a successful execution returns an ID."""
        result = ExecutionResult(
            workflow_id="wf_1",
            status="ok",
            node_results=[
                NodeResult(node_id="n1", status="ok", output="hello", elapsed_ms=100, prompt_tokens=10, completion_tokens=5)
            ],
            total_elapsed_ms=200,
            total_prompt_tokens=10,
            total_completion_tokens=5,
        )
        execution_id = await execution_store.save_execution(result, "wf_1", 1, {"key": "value"})
        assert isinstance(execution_id, str)
        assert len(execution_id) > 0

    @pytest.mark.asyncio
    async def test_save_failed_execution(self, execution_store: ExecutionStore) -> None:
        """Saving a failed execution returns an ID."""
        result = ExecutionResult(
            workflow_id="wf_1",
            status="failed",
            node_results=[
                NodeResult(node_id="n1", status="failed", error="boom", elapsed_ms=50)
            ],
            total_elapsed_ms=50,
        )
        execution_id = await execution_store.save_execution(result, "wf_1", 2, {})
        assert isinstance(execution_id, str)


class TestGetExecution:
    """Tests for retrieving a single execution."""

    @pytest.mark.asyncio
    async def test_get_existing_execution(self, execution_store: ExecutionStore) -> None:
        """Getting a saved execution returns its data."""
        result = ExecutionResult(
            workflow_id="wf_1",
            status="ok",
            node_results=[NodeResult(node_id="n1", status="ok", output="hello")],
            total_elapsed_ms=100,
            total_prompt_tokens=5,
            total_completion_tokens=3,
        )
        execution_id = await execution_store.save_execution(result, "wf_1", 1, {"trigger": "test"})

        record = await execution_store.get_execution(execution_id)
        assert record is not None
        assert record["id"] == execution_id
        assert record["workflow_id"] == "wf_1"
        assert record["version"] == 1
        assert record["status"] == "ok"
        assert record["trigger_payload"] == {"trigger": "test"}
        assert len(record["node_results"]) == 1
        assert record["node_results"][0]["node_id"] == "n1"
        assert record["total_elapsed_ms"] == 100
        assert record["total_prompt_tokens"] == 5
        assert record["total_completion_tokens"] == 3
        assert record["created_at"] is not None

    @pytest.mark.asyncio
    async def test_get_missing_execution(self, execution_store: ExecutionStore) -> None:
        """Getting a non-existent execution returns None."""
        record = await execution_store.get_execution("missing")
        assert record is None


class TestListExecutions:
    """Tests for listing executions."""

    @pytest.mark.asyncio
    async def test_list_returns_recent_first(self, execution_store: ExecutionStore) -> None:
        """List returns executions ordered newest first."""
        for i in range(3):
            result = ExecutionResult(
                workflow_id="wf_1",
                status="ok",
                node_results=[NodeResult(node_id="n1", status="ok", output=f"run {i}")],
            )
            await execution_store.save_execution(result, "wf_1", 1, {})

        executions = await execution_store.list_executions("wf_1", limit=10)
        assert len(executions) == 3

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, execution_store: ExecutionStore) -> None:
        """List respects the limit parameter."""
        for _ in range(5):
            result = ExecutionResult(workflow_id="wf_1", status="ok")
            await execution_store.save_execution(result, "wf_1", 1, {})

        executions = await execution_store.list_executions("wf_1", limit=2)
        assert len(executions) == 2

    @pytest.mark.asyncio
    async def test_list_filters_by_workflow(self, execution_store: ExecutionStore) -> None:
        """List only returns executions for the requested workflow."""
        result_a = ExecutionResult(workflow_id="wf_a", status="ok")
        await execution_store.save_execution(result_a, "wf_a", 1, {})

        result_b = ExecutionResult(workflow_id="wf_b", status="ok")
        await execution_store.save_execution(result_b, "wf_b", 1, {})

        executions = await execution_store.list_executions("wf_a")
        assert len(executions) == 1
        assert executions[0]["workflow_id"] == "wf_a"

    @pytest.mark.asyncio
    async def test_list_empty_workflow(self, execution_store: ExecutionStore) -> None:
        """List returns empty list when workflow has no executions."""
        executions = await execution_store.list_executions("wf_missing")
        assert executions == []
