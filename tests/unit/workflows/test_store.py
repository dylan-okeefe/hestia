"""Unit tests for WorkflowStore."""

from __future__ import annotations

import pytest
import pytest_asyncio

from hestia.persistence.db import Database
from hestia.persistence.schema import workflows
from hestia.workflows.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowVersion
from hestia.workflows.store import WorkflowStore


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database for testing."""
    database = Database(url="sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def store(db):
    """Create a WorkflowStore for testing."""
    return WorkflowStore(db)


class TestCreateTables:
    """Tests for create_tables method."""

    @pytest.mark.asyncio
    async def test_create_tables_idempotent(self, db):
        """create_tables is safe to call multiple times."""
        store = WorkflowStore(db)
        await store.create_tables()
        await store.create_tables()
        # No exception means success


class TestSaveWorkflow:
    """Tests for save_workflow."""

    @pytest.mark.asyncio
    async def test_save_new_workflow(self, store):
        """Can save a new workflow."""
        wf = Workflow(id="wf_1", name="Test Workflow")
        saved = await store.save_workflow(wf)

        assert saved.id == "wf_1"
        assert saved.name == "Test Workflow"
        assert saved.created_at is not None
        assert saved.updated_at is not None

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, store):
        """Saving with same ID updates the existing workflow."""
        wf = Workflow(id="wf_1", name="Original")
        await store.save_workflow(wf)

        wf.name = "Updated"
        updated = await store.save_workflow(wf)

        assert updated.name == "Updated"

        fetched = await store.get_workflow("wf_1")
        assert fetched is not None
        assert fetched.name == "Updated"

    @pytest.mark.asyncio
    async def test_save_preserves_trigger_config(self, store):
        """Trigger config round-trips through save/get."""
        wf = Workflow(
            id="wf_1",
            name="Trigger Test",
            trigger_type="cron",
            trigger_config={"expression": "0 9 * * *"},
        )
        await store.save_workflow(wf)

        fetched = await store.get_workflow("wf_1")
        assert fetched is not None
        assert fetched.trigger_type == "cron"
        assert fetched.trigger_config == {"expression": "0 9 * * *"}


class TestGetWorkflow:
    """Tests for get_workflow."""

    @pytest.mark.asyncio
    async def test_get_existing(self, store):
        """Can retrieve a saved workflow."""
        wf = Workflow(id="wf_1", name="Test", description="A test workflow")
        await store.save_workflow(wf)

        fetched = await store.get_workflow("wf_1")
        assert fetched is not None
        assert fetched.id == "wf_1"
        assert fetched.name == "Test"
        assert fetched.description == "A test workflow"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store):
        """Returns None for missing workflow."""
        result = await store.get_workflow("nonexistent")
        assert result is None


class TestListWorkflows:
    """Tests for list_workflows."""

    @pytest.mark.asyncio
    async def test_list_empty(self, store):
        """Empty store returns empty list."""
        workflows = await store.list_workflows()
        assert workflows == []

    @pytest.mark.asyncio
    async def test_list_ordered_by_name(self, store):
        """Workflows are ordered by name."""
        await store.save_workflow(Workflow(id="wf_b", name="Beta"))
        await store.save_workflow(Workflow(id="wf_a", name="Alpha"))
        await store.save_workflow(Workflow(id="wf_c", name="Charlie"))

        workflows = await store.list_workflows()
        names = [w.name for w in workflows]
        assert names == ["Alpha", "Beta", "Charlie"]


class TestDeleteWorkflow:
    """Tests for delete_workflow."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, store):
        """Can delete a workflow."""
        wf = Workflow(id="wf_1", name="To Delete")
        await store.save_workflow(wf)

        result = await store.delete_workflow("wf_1")
        assert result is True

        fetched = await store.get_workflow("wf_1")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_cascades_versions(self, store):
        """Deleting a workflow removes its versions."""
        wf = Workflow(id="wf_1", name="To Delete")
        await store.save_workflow(wf)

        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[WorkflowNode(id="n1", type="start", label="Start")],
        )
        await store.save_version(version)

        await store.delete_workflow("wf_1")

        versions = await store.list_versions("wf_1")
        assert versions == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        """Deleting missing workflow returns False."""
        result = await store.delete_workflow("nonexistent")
        assert result is False


class TestSaveVersion:
    """Tests for save_version."""

    @pytest.mark.asyncio
    async def test_save_new_version(self, store):
        """Can save a new version."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[WorkflowNode(id="n1", type="start", label="Start")],
            edges=[WorkflowEdge(id="e1", source_node_id="n1", target_node_id="n2")],
        )
        saved = await store.save_version(version)

        assert saved.workflow_id == "wf_1"
        assert saved.version == 1
        assert len(saved.nodes) == 1
        assert len(saved.edges) == 1

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, store):
        """Saving same version updates it."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        v1 = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[WorkflowNode(id="n1", type="start", label="Start")],
        )
        await store.save_version(v1)

        v1.nodes = [
            WorkflowNode(id="n1", type="start", label="Start"),
            WorkflowNode(id="n2", type="end", label="End"),
        ]
        await store.save_version(v1)

        fetched = await store.list_versions("wf_1")
        assert len(fetched) == 1
        assert len(fetched[0].nodes) == 2

    @pytest.mark.asyncio
    async def test_save_version_round_trips_nodes_and_edges(self, store):
        """Nodes and edges are preserved through save/get."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        version = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[
                WorkflowNode(
                    id="n1",
                    type="start",
                    label="Start",
                    config={"key": "value"},
                    position={"x": 10.5, "y": 20.0},
                ),
            ],
            edges=[
                WorkflowEdge(
                    id="e1",
                    source_node_id="n1",
                    target_node_id="n2",
                    source_handle="out",
                    target_handle="in",
                    condition="x > 0",
                ),
            ],
        )
        await store.save_version(version)

        versions = await store.list_versions("wf_1")
        assert len(versions) == 1
        v = versions[0]
        assert len(v.nodes) == 1
        assert v.nodes[0].config == {"key": "value"}
        assert v.nodes[0].position == {"x": 10.5, "y": 20.0}
        assert len(v.edges) == 1
        assert v.edges[0].source_handle == "out"
        assert v.edges[0].target_handle == "in"
        assert v.edges[0].condition == "x > 0"


class TestGetActiveVersion:
    """Tests for get_active_version."""

    @pytest.mark.asyncio
    async def test_get_active_version(self, store):
        """Returns the active version."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        v1 = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[WorkflowNode(id="n1", type="start", label="V1")],
            is_active=True,
        )
        await store.save_version(v1)

        active = await store.get_active_version("wf_1")
        assert active is not None
        assert active.version == 1
        assert active.nodes[0].label == "V1"

    @pytest.mark.asyncio
    async def test_get_active_none(self, store):
        """Returns None when no version is active."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        v1 = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[],
            is_active=False,
        )
        await store.save_version(v1)

        active = await store.get_active_version("wf_1")
        assert active is None

    @pytest.mark.asyncio
    async def test_get_active_nonexistent_workflow(self, store):
        """Returns None for missing workflow."""
        active = await store.get_active_version("nonexistent")
        assert active is None


class TestListVersions:
    """Tests for list_versions."""

    @pytest.mark.asyncio
    async def test_list_versions(self, store):
        """Lists versions newest first."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        for i in range(3):
            v = WorkflowVersion(
                workflow_id="wf_1",
                version=i + 1,
                nodes=[WorkflowNode(id="n1", type="start", label=f"V{i + 1}")],
            )
            await store.save_version(v)

        versions = await store.list_versions("wf_1")
        assert len(versions) == 3
        assert [v.version for v in versions] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_list_versions_empty(self, store):
        """Empty list for workflow with no versions."""
        versions = await store.list_versions("nonexistent")
        assert versions == []


class TestActivateVersion:
    """Tests for activate_version."""

    @pytest.mark.asyncio
    async def test_activate_version(self, store):
        """Can activate a specific version."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        for i in range(3):
            v = WorkflowVersion(
                workflow_id="wf_1",
                version=i + 1,
                nodes=[],
            )
            await store.save_version(v)

        result = await store.activate_version("wf_1", 2)
        assert result is True

        active = await store.get_active_version("wf_1")
        assert active is not None
        assert active.version == 2

    @pytest.mark.asyncio
    async def test_activate_deactivates_others(self, store):
        """Activating one version deactivates all others."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        v1 = WorkflowVersion(workflow_id="wf_1", version=1, nodes=[], is_active=False)
        v2 = WorkflowVersion(workflow_id="wf_1", version=2, nodes=[], is_active=False)
        await store.save_version(v1)
        await store.save_version(v2)

        await store.activate_version("wf_1", 2)

        versions = await store.list_versions("wf_1")
        active_count = sum(1 for v in versions if v.is_active)
        assert active_count == 1
        assert versions[0].version == 2
        assert versions[0].is_active is True

    @pytest.mark.asyncio
    async def test_activate_nonexistent_version(self, store):
        """Returns False for missing version."""
        wf = Workflow(id="wf_1", name="Test")
        await store.save_workflow(wf)

        result = await store.activate_version("wf_1", 999)
        assert result is False

    @pytest.mark.asyncio
    async def test_activate_nonexistent_workflow(self, store):
        """Returns False for missing workflow."""
        result = await store.activate_version("nonexistent", 1)
        assert result is False


class TestGetActiveVersionsBatch:
    """Tests for get_active_versions_batch."""

    @pytest.mark.asyncio
    async def test_batch_returns_active_versions(self, store):
        """Fetches active versions for multiple workflows in one query."""
        wf1 = Workflow(id="wf_1", name="A")
        wf2 = Workflow(id="wf_2", name="B")
        await store.save_workflow(wf1)
        await store.save_workflow(wf2)

        v1 = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[WorkflowNode(id="n1", type="start", label="V1")],
            is_active=True,
        )
        v2 = WorkflowVersion(
            workflow_id="wf_2",
            version=1,
            nodes=[WorkflowNode(id="n2", type="start", label="V2")],
            is_active=True,
        )
        await store.save_version(v1)
        await store.save_version(v2)

        result = await store.get_active_versions_batch(["wf_1", "wf_2"])
        assert result["wf_1"] is not None
        assert result["wf_1"].version == 1
        assert result["wf_2"] is not None
        assert result["wf_2"].version == 1

    @pytest.mark.asyncio
    async def test_batch_returns_none_for_inactive(self, store):
        """Returns None for workflows with no active version."""
        wf = Workflow(id="wf_1", name="A")
        await store.save_workflow(wf)

        v1 = WorkflowVersion(
            workflow_id="wf_1",
            version=1,
            nodes=[WorkflowNode(id="n1", type="start", label="V1")],
            is_active=False,
        )
        await store.save_version(v1)

        result = await store.get_active_versions_batch(["wf_1"])
        assert result["wf_1"] is None

    @pytest.mark.asyncio
    async def test_batch_empty_input(self, store):
        """Empty list returns empty dict."""
        result = await store.get_active_versions_batch([])
        assert result == {}


class TestUpsertHelper:
    """Tests for the internal _upsert helper."""

    @pytest.mark.asyncio
    async def test_upsert_insert_and_update(self, store):
        """_upsert inserts new rows and updates existing ones."""
        wf = Workflow(id="wf_upsert", name="Original")
        await store.save_workflow(wf)

        # Update via upsert
        values = {
            "id": "wf_upsert",
            "name": "Updated",
            "description": "",
            "trigger_type": "manual",
            "trigger_config": "{}",
            "owner_id": "",
            "trust_level": "paranoid",
            "created_at": wf.created_at,
            "updated_at": wf.updated_at,
        }
        await store._upsert(
            workflows,
            values,
            conflict_keys=["id"],
            update_keys=[
                "name",
                "description",
                "trigger_type",
                "trigger_config",
                "owner_id",
                "trust_level",
                "updated_at",
            ],
        )

        fetched = await store.get_workflow("wf_upsert")
        assert fetched is not None
        assert fetched.name == "Updated"


class TestRowConverters:
    """Tests for edge cases in row conversion."""

    def test_row_to_workflow_bad_json(self, store):
        """Bad trigger_config JSON is handled gracefully."""
        from types import SimpleNamespace

        row = SimpleNamespace(
            id="wf_1",
            name="Test",
            description="Desc",
            trigger_type="manual",
            trigger_config="not json",
            created_at=None,
            updated_at=None,
        )
        wf = store._row_to_workflow(row)
        assert wf.trigger_config == {}

    def test_row_to_version_bad_json(self, store):
        """Bad nodes/edges JSON is handled gracefully."""
        from types import SimpleNamespace

        row = SimpleNamespace(
            workflow_id="wf_1",
            version=1,
            nodes="not json",
            edges="also not json",
            created_at=None,
            is_active=True,
        )
        version = store._row_to_version(row)
        assert version.nodes == []
        assert version.edges == []

    def test_row_to_version_null_active(self, store):
        """NULL is_active defaults to False."""
        from types import SimpleNamespace

        row = SimpleNamespace(
            workflow_id="wf_1",
            version=1,
            nodes="[]",
            edges="[]",
            created_at=None,
            is_active=None,
        )
        version = store._row_to_version(row)
        assert version.is_active is False
