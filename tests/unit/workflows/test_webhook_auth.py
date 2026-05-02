"""Tests for webhook authentication."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.web.api import create_web_app
from hestia.web.context import WebContext, set_web_context
from hestia.workflows.models import Workflow


@pytest.fixture(autouse=True)
def _clear_web_context() -> None:
    """Clear the global web context before each test."""
    from hestia.web import context as ctx_mod

    ctx_mod._ctx = None


@pytest.fixture
def mock_app() -> MagicMock:
    """Provide a mocked AppContext."""
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
        auth_enabled=False,
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
    return mock


@pytest.fixture
def client(mock_app: MagicMock) -> TestClient:
    """Create a TestClient with all stores mocked."""
    ctx = WebContext(
        session_store=AsyncMock(),
        proposal_store=AsyncMock(),
        style_store=AsyncMock(),
        scheduler_store=AsyncMock(),
        trace_store=AsyncMock(),
        failure_store=AsyncMock(),
        workflow_store=AsyncMock(),
        execution_store=AsyncMock(),
        app=mock_app,
        auth_manager=None,
    )
    set_web_context(ctx)
    app = create_web_app()
    return TestClient(app)


class TestWebhookHMAC:
    """Tests for HMAC signature validation on webhook endpoints."""

    def test_valid_hmac_returns_202(self, client: TestClient, mock_app: MagicMock) -> None:
        """A request with a valid HMAC signature is accepted."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        mock_event_bus = AsyncMock()
        mock_app.event_bus = mock_event_bus
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        payload = {"key": "value"}
        body_bytes = json.dumps(payload).encode()
        signature = hmac.new(b"super-secret", body_bytes, hashlib.sha256).hexdigest()

        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
        )
        assert response.status_code == 202
        assert response.json()["received"] is True
        mock_event_bus.publish.assert_awaited_once()

    def test_missing_header_returns_401(self, client: TestClient, mock_app: MagicMock) -> None:
        """A request without the X-Webhook-Signature header is rejected."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        response = client.post("/api/webhooks/deploy", json={"key": "value"})
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]

    def test_invalid_signature_returns_401(self, client: TestClient, mock_app: MagicMock) -> None:
        """A request with an incorrect HMAC signature is rejected."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        response = client.post(
            "/api/webhooks/deploy",
            json={"key": "value"},
            headers={"X-Webhook-Signature": "bad-signature"},
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_unknown_endpoint_returns_404(self, client: TestClient, mock_app: MagicMock) -> None:
        """A request to an endpoint with no matching workflow returns 404."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[])

        response = client.post("/api/webhooks/unknown", json={"key": "value"})
        assert response.status_code == 404

    def test_empty_body_with_valid_hmac(self, client: TestClient, mock_app: MagicMock) -> None:
        """Webhook with empty body and valid HMAC of empty string returns 202."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        mock_event_bus = AsyncMock()
        mock_app.event_bus = mock_event_bus
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        body_bytes = b""
        signature = hmac.new(b"super-secret", body_bytes, hashlib.sha256).hexdigest()
        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={"X-Webhook-Signature": signature},
        )
        assert response.status_code == 202

    def test_non_json_body_with_valid_hmac(self, client: TestClient, mock_app: MagicMock) -> None:
        """Webhook with plain text body and valid HMAC returns 202."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        mock_event_bus = AsyncMock()
        mock_app.event_bus = mock_event_bus
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        body_bytes = b"plain text payload"
        signature = hmac.new(b"super-secret", body_bytes, hashlib.sha256).hexdigest()
        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={"X-Webhook-Signature": signature, "Content-Type": "text/plain"},
        )
        assert response.status_code == 202

    def test_replay_attack_same_signature_twice(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """Same valid signature sent twice — both succeed (no nonce in v1)."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        mock_event_bus = AsyncMock()
        mock_app.event_bus = mock_event_bus
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        payload = {"key": "value"}
        body_bytes = json.dumps(payload).encode()
        signature = hmac.new(b"super-secret", body_bytes, hashlib.sha256).hexdigest()

        for _ in range(2):
            response = client.post(
                "/api/webhooks/deploy",
                content=body_bytes,
                headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
            )
            assert response.status_code == 202


class TestAutoGenerateSecret:
    """Tests for auto-generating webhook secrets on workflow creation."""

    def test_auto_generates_secret_on_create(self, client: TestClient, mock_app: MagicMock) -> None:
        """Creating a webhook workflow without a secret auto-generates one."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.save_workflow = AsyncMock(return_value=None)

        response = client.post(
            "/api/workflows",
            json={
                "name": "Webhook Workflow",
                "trigger_type": "webhook",
                "trigger_config": {"endpoint": "deploy"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data["trigger_config"]
        assert len(data["trigger_config"]["secret"]) > 0
        ctx.workflow_store.save_workflow.assert_awaited_once()

    def test_does_not_override_provided_secret(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """Creating a webhook workflow with an explicit secret preserves it."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.save_workflow = AsyncMock(return_value=None)

        response = client.post(
            "/api/workflows",
            json={
                "name": "Webhook Workflow",
                "trigger_type": "webhook",
                "trigger_config": {"endpoint": "deploy", "secret": "custom-secret"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_config"]["secret"] == "custom-secret"


class TestExposeWebhookURL:
    """Tests for exposing webhook URL and secret in GET workflow response."""

    def test_get_workflow_includes_webhook_fields(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """GET /workflows/{id} includes webhook_url and secret for webhook triggers."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "shh"},
        )
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.get_active_version = AsyncMock(return_value=None)

        response = client.get("/api/workflows/wf1")
        assert response.status_code == 200
        data = response.json()
        assert data["webhook_url"] == "http://testserver/api/webhooks/deploy"
        assert data["secret"] == "shh"

    def test_get_workflow_omits_webhook_fields_for_non_webhook(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """GET /workflows/{id} omits webhook_url and secret for non-webhook triggers."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Manual",
            trigger_type="manual",
        )
        ctx.workflow_store.get_workflow = AsyncMock(return_value=wf)
        ctx.workflow_store.get_active_version = AsyncMock(return_value=None)

        response = client.get("/api/workflows/wf1")
        assert response.status_code == 200
        data = response.json()
        assert "webhook_url" not in data
        assert "secret" not in data
