"""L245 round-2 V2: the 409-plus-confirm activation flow, end to end.

The operator-facing half of allowlist-only authorization: save returns the
derived set, unconfirmed activation of an authorization change fails with
409 + diff, confirmation activates and persists the grant against a REAL
WorkflowStore (no mocks on the authorization path).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: F401

from hestia.persistence.db import Database
from hestia.web.api import create_web_app
from hestia.web.context import WebContext, set_web_context
from hestia.workflows.store import WorkflowStore


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/l245-e2e.db")
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def workflow_store(db) -> WorkflowStore:
    store = WorkflowStore(db)
    await store.create_tables()
    return store


@pytest.fixture
def app_ctx() -> MagicMock:
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.features = MagicMock()
    mock.config.features.web = MagicMock(auth_enabled=False)
    return mock


@pytest.fixture
def client(app_ctx: MagicMock, workflow_store: WorkflowStore) -> TestClient:
    ctx = WebContext(
        session_store=AsyncMock(),
        message_store=AsyncMock(),
        turn_store=AsyncMock(),
        handoff_service=AsyncMock(),
        proposal_store=AsyncMock(),
        style_store=AsyncMock(),
        scheduler_store=AsyncMock(),
        trace_store=AsyncMock(),
        failure_store=AsyncMock(),
        workflow_store=workflow_store,
        execution_store=AsyncMock(),
        error_resolution_store=AsyncMock(),
        app=app_ctx,
        auth_manager=None,
        user_store=AsyncMock(),
        scheduler=None,
    )
    set_web_context(ctx)
    return TestClient(create_web_app())


def _node(nid: str, type_: str, **config) -> dict:
    return {
        "id": nid,
        "type": type_,
        "position": {"x": 0, "y": 0},
        "data": {"label": nid, **config},
    }


class TestActivationFlowEndToEnd:
    async def _stored_allow_set(self, workflow_store: WorkflowStore, wf_id: str) -> set[str]:
        wf = await workflow_store.get_workflow(wf_id)
        assert wf is not None
        return set(wf.allow_listed_tools or set())

    @pytest.mark.asyncio
    async def test_save_activate_409_confirm_flow(
        self, client: TestClient, workflow_store: WorkflowStore
    ) -> None:
        # 1. Create a workflow.
        created = client.post("/api/workflows", json={"name": "E2E Auth"}).json()
        wf_id = created["id"]

        # 2. Save version 1 granting terminal.
        v1 = client.post(
            f"/api/workflows/{wf_id}/versions",
            json={"nodes": [_node("n1", "tool_call", tool_name="terminal")], "edges": []},
        ).json()
        assert v1["derived_allow_list"] == ["terminal"]

        # 3. First-ever activation changes the grant from {} -> {terminal}:
        #    refused until confirmed, with the exact diff.
        r = client.post(f"/api/workflows/{wf_id}/versions/{wf_id}:1/activate")
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "allow_list_changed"
        assert detail["allow_list_diff"]["added"] == ["terminal"]
        assert detail["allow_list_diff"]["removed"] == []
        # Nothing flipped active behind the refusal.
        assert await workflow_store.get_active_version(wf_id) is None
        assert await self._stored_allow_set(workflow_store, wf_id) == set()

        # 4. Confirmed retry activates and persists the derived grant.
        r = client.post(
            f"/api/workflows/{wf_id}/versions/{wf_id}:1/activate"
            "?confirm_allow_list_change=true"
        )
        assert r.status_code == 200
        assert r.json()["activated"] is True
        active = await workflow_store.get_active_version(wf_id)
        assert active is not None and active.version == 1
        assert await self._stored_allow_set(workflow_store, wf_id) == {"terminal"}

        # 5. Version 2 widens the grant (adds investigate over read_file).
        v2 = client.post(
            f"/api/workflows/{wf_id}/versions",
            json={
                "nodes": [
                    _node("n1", "tool_call", tool_name="terminal"),
                    _node("n2", "investigate", tools=["read_file"]),
                ],
                "edges": [],
            },
        ).json()
        assert sorted(v2["derived_allow_list"]) == ["read_file", "terminal"]

        # 6. Unconfirmed re-activation: 409 with only the delta.
        r = client.post(f"/api/workflows/{wf_id}/versions/{wf_id}:2/activate")
        assert r.status_code == 409
        diff = r.json()["detail"]["allow_list_diff"]
        assert diff["added"] == ["read_file"]
        assert diff["removed"] == []
        # Active version unchanged during review.
        active = await workflow_store.get_active_version(wf_id)
        assert active is not None and active.version == 1

        # 7. Confirmed: grant widened, version live.
        r = client.post(
            f"/api/workflows/{wf_id}/versions/{wf_id}:2/activate"
            "?confirm_allow_list_change=true"
        )
        assert r.status_code == 200
        assert await self._stored_allow_set(workflow_store, wf_id) == {
            "read_file",
            "terminal",
        }
        active = await workflow_store.get_active_version(wf_id)
        assert active is not None and active.version == 2

    @pytest.mark.asyncio
    async def test_unchanged_grant_activates_without_confirmation(
        self, client: TestClient, workflow_store: WorkflowStore
    ) -> None:
        """Re-saving an identical graph produces no authorization delta, so
        plain activation works - the friction only exists on change."""
        created = client.post("/api/workflows", json={"name": "No-Delta"}).json()
        wf_id = created["id"]
        nodes = {"nodes": [_node("n1", "tool_call", tool_name="read_file")], "edges": []}

        client.post(f"/api/workflows/{wf_id}/versions", json=nodes)
        r = client.post(
            f"/api/workflows/{wf_id}/versions/{wf_id}:1/activate"
            "?confirm_allow_list_change=true"
        )
        assert r.status_code == 200

        # Same graph again as version 2: identical derived set.
        client.post(f"/api/workflows/{wf_id}/versions", json=nodes)
        r = client.post(f"/api/workflows/{wf_id}/versions/{wf_id}:2/activate")
        assert r.status_code == 200
        active = await workflow_store.get_active_version(wf_id)
        assert active is not None and active.version == 2

    @pytest.mark.asyncio
    async def test_narrowing_requires_confirmation_too(
        self, client: TestClient, workflow_store: WorkflowStore
    ) -> None:
        """Revoking a tool is also an authorization change: 409 shows the
        removal, confirmation applies it."""
        created = client.post("/api/workflows", json={"name": "Narrowing"}).json()
        wf_id = created["id"]
        wide = {
            "nodes": [
                _node("n1", "tool_call", tool_name="terminal"),
                _node("n2", "tool_call", tool_name="read_file"),
            ],
            "edges": [],
        }
        narrow = {
            "nodes": [_node("n1", "tool_call", tool_name="read_file")],
            "edges": [],
        }

        client.post(f"/api/workflows/{wf_id}/versions", json=wide)
        client.post(
            f"/api/workflows/{wf_id}/versions/{wf_id}:1/activate"
            "?confirm_allow_list_change=true"
        )

        client.post(f"/api/workflows/{wf_id}/versions", json=narrow)
        r = client.post(f"/api/workflows/{wf_id}/versions/{wf_id}:2/activate")
        assert r.status_code == 409
        diff = r.json()["detail"]["allow_list_diff"]
        assert diff["added"] == []
        assert diff["removed"] == ["terminal"]

        r = client.post(
            f"/api/workflows/{wf_id}/versions/{wf_id}:2/activate"
            "?confirm_allow_list_change=true"
        )
        assert r.status_code == 200
        assert await self._stored_allow_set(workflow_store, wf_id) == {"read_file"}
