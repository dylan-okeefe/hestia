"""Tests for webhook authentication."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.web.api import create_web_app
from hestia.web.context import WebContext, set_web_context
from hestia.workflows.models import Workflow


def _sign(secret: str, body_bytes: bytes, timestamp: int | None = None) -> tuple[str, int]:
    """Compute webhook signature over timestamp.body."""
    if timestamp is None:
        timestamp = int(time.time())
    payload = f"{timestamp}.".encode() + body_bytes
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return signature, timestamp


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
        error_resolution_store=AsyncMock(),
        app=mock_app,
        auth_manager=None,
        user_store=AsyncMock(),
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
        signature, timestamp = _sign("super-secret", body_bytes)

        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 202
        assert response.json()["received"] is True
        mock_event_bus.publish.assert_awaited_once()

    def test_missing_timestamp_returns_401(self, client: TestClient, mock_app: MagicMock) -> None:
        """A request without the X-Webhook-Timestamp header is rejected."""
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
        assert "Timestamp" in response.json()["detail"]

    def test_missing_signature_returns_401(self, client: TestClient, mock_app: MagicMock) -> None:
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

        response = client.post(
            "/api/webhooks/deploy",
            json={"key": "value"},
            headers={"X-Webhook-Timestamp": str(int(time.time()))},
        )
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]
        assert "Signature" in response.json()["detail"]

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
            headers={
                "X-Webhook-Signature": "bad-signature",
                "X-Webhook-Timestamp": str(int(time.time())),
            },
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
        signature, timestamp = _sign("super-secret", body_bytes)
        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
            },
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
        signature, timestamp = _sign("super-secret", body_bytes)
        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
                "Content-Type": "text/plain",
            },
        )
        assert response.status_code == 202

    def test_replay_attack_same_signature_twice(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """Same valid signature sent twice — second request is rejected."""
        from hestia.web import context as ctx_mod
        from hestia.web.routes import webhooks as webhooks_mod
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

        # Clear the seen-signatures cache so this test is independent
        webhooks_mod._seen_signatures.clear()

        payload = {"key": "value"}
        body_bytes = json.dumps(payload).encode()
        signature, timestamp = _sign("super-secret", body_bytes)

        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 202
        assert response.json()["received"] is True
        mock_event_bus.publish.assert_awaited_once()

        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 409
        assert "duplicate" in response.json()["detail"].lower()

    def test_replay_with_stale_timestamp_returns_401(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """A replay with a timestamp outside the ±5-minute window is rejected."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy", "secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        payload = {"key": "value"}
        body_bytes = json.dumps(payload).encode()
        stale_timestamp = int(time.time()) - 400
        signature, _ = _sign("super-secret", body_bytes, stale_timestamp)

        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(stale_timestamp),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401
        assert "replay" in response.json()["detail"].lower()

    def test_no_wildcard_match(self, client: TestClient, mock_app: MagicMock) -> None:
        """A workflow without an explicit endpoint does NOT match arbitrary paths."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"secret": "super-secret"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        response = client.post("/api/webhooks/arbitrary", json={"key": "value"})
        assert response.status_code == 404

    def test_secretless_workflow_returns_401(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """A workflow with no configured secret is un-triggerable (fail-closed)."""
        from hestia.web import context as ctx_mod
        from hestia.workflows.models import Workflow

        ctx = ctx_mod._ctx
        assert ctx is not None
        wf = Workflow(
            id="wf1",
            name="Hook",
            trigger_type="webhook",
            trigger_config={"endpoint": "deploy"},
        )
        ctx.workflow_store.list_workflows = AsyncMock(return_value=[wf])

        response = client.post(
            "/api/webhooks/deploy",
            json={"key": "value"},
            headers={
                "X-Webhook-Timestamp": str(int(time.time())),
                "X-Webhook-Signature": "abc123",
            },
        )
        assert response.status_code == 401
        assert "secret" in response.json()["detail"].lower()

    def test_auth_headers_stripped_from_event(
        self, client: TestClient, mock_app: MagicMock
    ) -> None:
        """Sensitive auth headers are not published in the event payload."""
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
        signature, timestamp = _sign("super-secret", body_bytes)

        response = client.post(
            "/api/webhooks/deploy",
            content=body_bytes,
            headers={
                "X-Webhook-Signature": signature,
                "X-Webhook-Timestamp": str(timestamp),
                "Content-Type": "application/json",
                "Authorization": "Bearer secret-token",
                "Cookie": "session=abc",
            },
        )
        assert response.status_code == 202
        call_args = mock_event_bus.publish.call_args
        published_headers = call_args[0][1]["headers"]
        assert "x-webhook-signature" not in {k.lower() for k in published_headers}
        assert "authorization" not in {k.lower() for k in published_headers}
        assert "cookie" not in {k.lower() for k in published_headers}
        assert "content-type" in {k.lower() for k in published_headers}


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
