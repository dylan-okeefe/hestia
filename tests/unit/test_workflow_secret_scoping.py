"""Tests for workflow webhook secret redaction and owner scoping."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from hestia.web.api import create_web_app
from hestia.web.context import WebContext, set_web_context
from hestia.workflows.models import Workflow


class _TestUserMiddleware(BaseHTTPMiddleware):
    """Set request.state identity from test headers.

    This mirrors what AuthMiddleware does in production without requiring
    session token management in unit tests.
    """

    async def dispatch(self, request, call_next: RequestResponseEndpoint):
        platform_user = request.headers.get("X-Test-Platform-User")
        user_id = request.headers.get("X-Test-User-Id")
        if platform_user:
            request.state.platform_user = platform_user
        if user_id:
            request.state.user_id = user_id
        return await call_next(request)


@pytest.fixture(autouse=True)
def _clear_web_context() -> None:
    """Clear the global web context before each test."""
    from hestia.web import context as ctx_mod

    ctx_mod._ctx = None


@pytest.fixture
def mock_app() -> MagicMock:
    """Provide a mocked AppContext with auth enabled."""
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.telegram = MagicMock(bot_token="", allowed_users=[])
    mock.config.matrix = MagicMock(homeserver="", user_id="", access_token="", allowed_rooms=[])
    mock.config.email = MagicMock(imap_host="", username="", password="", password_env="")
    mock.config.storage = MagicMock(allowed_roots=["."])
    mock.config.inference = MagicMock(base_url="")
    mock.config.security = MagicMock(injection_scanner_enabled=False)
    mock.config.web_search = MagicMock()
    mock.config.trust = MagicMock(preset=None)
    mock.config.rate_limit = MagicMock()
    mock.config.features = MagicMock()
    mock.config.features.web = MagicMock(
        enabled=True,
        host="127.0.0.1",
        port=8080,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )
    mock.config.features.rate_limit = MagicMock()
    mock.config.features.policy = MagicMock()
    mock.config.features.style = MagicMock()
    mock.config.features.reflection = MagicMock()
    mock.config.features.compression = MagicMock()
    mock.config.features.handoff = MagicMock()
    mock.config.features.security = MagicMock()
    mock.config.features.web_search = MagicMock()
    mock.tool_registry = MagicMock()
    mock.tool_registry.list_names.return_value = []
    mock.event_bus = AsyncMock()
    return mock


@pytest.fixture
def client(mock_app: MagicMock) -> TestClient:
    """Create a TestClient with identity-aware middleware."""
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
        workflow_store=AsyncMock(),
        execution_store=AsyncMock(),
        error_resolution_store=AsyncMock(),
        app=mock_app,
        auth_manager=None,
        user_store=AsyncMock(),
        scheduler=None,
    )
    ctx.execution_store.get_last_execution_per_workflow = AsyncMock(return_value={})
    set_web_context(ctx)
    app = create_web_app()
    app.add_middleware(_TestUserMiddleware)
    return TestClient(app)


def _webhook_workflow(owner_id: str = "owner_a") -> Workflow:
    return Workflow(
        id="wf_hook",
        name="Webhook Workflow",
        trigger_type="webhook",
        trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        owner_id=owner_id,
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def _manual_workflow(owner_id: str = "owner_a") -> Workflow:
    return Workflow(
        id="wf_manual",
        name="Manual Workflow",
        trigger_type="manual",
        owner_id=owner_id,
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


class TestListWorkflowsSecretRedaction:
    """GET /api/workflows must redact secrets and respect ownership."""

    def test_list_workflows_redacts_secret(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        ctx.workflow_store.list_workflows_for_owner = AsyncMock(return_value=[wf])
        ctx.workflow_store.get_active_versions_batch = AsyncMock(return_value={"wf_hook": None})

        response = client.get("/api/workflows", headers={"X-Test-Platform-User": "owner_a"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 1
        wf_data = data["workflows"][0]
        assert wf_data["trigger_config"]["has_secret"] is True
        assert wf_data["trigger_config"].get("secret") != "super-secret"
        ctx.workflow_store.list_workflows_for_owner.assert_awaited_once_with("owner_a", False)

    def test_list_workflows_owner_scoped(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.list_workflows_for_owner = AsyncMock(return_value=[])
        ctx.workflow_store.get_active_versions_batch = AsyncMock(return_value={})

        response = client.get("/api/workflows", headers={"X-Test-Platform-User": "owner_b"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 0
        ctx.workflow_store.list_workflows_for_owner.assert_awaited_once_with("owner_b", False)

    def test_list_workflows_admin_sees_all(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow(owner_id="owner_a")
        ctx.workflow_store.list_workflows_for_owner = AsyncMock(return_value=[wf])
        ctx.workflow_store.get_active_versions_batch = AsyncMock(return_value={"wf_hook": None})
        ctx.user_store.get_user = AsyncMock(return_value=MagicMock(role="admin"))

        response = client.get(
            "/api/workflows",
            headers={"X-Test-Platform-User": "admin_user", "X-Test-User-Id": "uid_admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) == 1
        ctx.workflow_store.list_workflows_for_owner.assert_awaited_once_with("admin_user", True)


class TestGetWorkflowSecretRedaction:
    """GET /api/workflows/{id} must redact secrets."""

    def test_get_workflow_redacts_secret(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.get_active_version = AsyncMock(return_value=None)

        response = client.get("/api/workflows/wf_hook", headers={"X-Test-Platform-User": "owner_a"})
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_config"]["has_secret"] is True
        assert data["trigger_config"].get("secret") != "super-secret"
        assert "webhook_url" in data

    def test_get_workflow_no_secret_no_webhook_url(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        wf.trigger_config = {"endpoint": "deploy"}  # secret missing
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.get_active_version = AsyncMock(return_value=None)

        response = client.get("/api/workflows/wf_hook", headers={"X-Test-Platform-User": "owner_a"})
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_config"]["has_secret"] is False
        assert "webhook_url" not in data


class TestCreateWorkflowSecretReveal:
    """POST /api/workflows must reveal the secret once on creation."""

    def test_create_workflow_reveals_secret_once(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.save_workflow = AsyncMock(return_value=None)

        response = client.post(
            "/api/workflows",
            json={"name": "New Hook", "trigger_type": "webhook"},
            headers={"X-Test-Platform-User": "owner_a"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_type"] == "webhook"
        assert data["trigger_config"]["has_secret"] is True
        assert "secret" in data["trigger_config"]
        assert len(data["trigger_config"]["secret"]) > 0


class TestUpdateWorkflowSecretHandling:
    """PUT /api/workflows/{id} must preserve secrets and return redacted responses."""

    def test_update_workflow_preserves_secret(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.save_workflow = AsyncMock(return_value=None)

        response = client.put(
            "/api/workflows/wf_hook",
            json={"trigger_config": {"endpoint": "deploy"}},
            headers={"X-Test-Platform-User": "owner_a"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_config"]["has_secret"] is True
        assert data["trigger_config"].get("secret") != "super-secret"
        saved_config = ctx.workflow_store.save_workflow.call_args[0][0].trigger_config
        assert saved_config["secret"] == "super-secret"

    def test_update_workflow_can_rotate_secret(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.save_workflow = AsyncMock(return_value=None)

        response = client.put(
            "/api/workflows/wf_hook",
            json={"trigger_config": {"endpoint": "deploy", "secret": "new-secret"}},
            headers={"X-Test-Platform-User": "owner_a"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_config"]["has_secret"] is True
        assert data["trigger_config"].get("secret") != "new-secret"
        saved_config = ctx.workflow_store.save_workflow.call_args[0][0].trigger_config
        assert saved_config["secret"] == "new-secret"


class TestRotateWorkflowSecret:
    """POST /api/workflows/{id}/rotate-secret must rotate secrets with access control."""

    def test_rotate_secret_owner(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.save_workflow = AsyncMock(return_value=None)

        response = client.post(
            "/api/workflows/wf_hook/rotate-secret",
            headers={"X-Test-Platform-User": "owner_a"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert data["secret"] != "super-secret"
        assert data["workflow"]["trigger_config"]["has_secret"] is True
        saved_config = ctx.workflow_store.save_workflow.call_args[0][0].trigger_config
        assert saved_config["secret"] == data["secret"]

    def test_rotate_secret_non_owner_forbidden(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _webhook_workflow()
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)

        response = client.post(
            "/api/workflows/wf_hook/rotate-secret",
            headers={"X-Test-Platform-User": "owner_b"},
        )
        assert response.status_code == 403

    def test_rotate_secret_non_webhook_bad_request(self, client: TestClient) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = _manual_workflow()
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)

        response = client.post(
            "/api/workflows/wf_manual/rotate-secret",
            headers={"X-Test-Platform-User": "owner_a"},
        )
        assert response.status_code == 400
