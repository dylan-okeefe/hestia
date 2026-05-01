"""Integration tests for the web auth flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.config import WebConfig
from hestia.web.api import create_web_app
from hestia.web.auth import AuthManager, AuthMiddleware
from hestia.web.context import WebContext, set_web_context


@pytest.fixture(autouse=True)
def _clear_web_context() -> None:
    from hestia.web import context as ctx_mod

    ctx_mod._ctx = None


@pytest.fixture
def mock_app() -> MagicMock:
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.telegram = MagicMock(bot_token="", allowed_users=[])
    mock.config.matrix = MagicMock(
        homeserver="", user_id="", access_token="", allowed_rooms=[]
    )
    mock.config.email = MagicMock(
        imap_host="", username="", password="", password_env=""
    )
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
    return mock


@pytest.fixture
def client(mock_app: MagicMock) -> TestClient:
    telegram_adapter = MagicMock()
    telegram_adapter._config = MagicMock(allowed_users=["12345"])
    telegram_adapter.send_message = AsyncMock(return_value="msg_1")

    matrix_adapter = MagicMock()
    matrix_adapter._config = MagicMock(allowed_rooms=["!room:matrix.org"])
    matrix_adapter.send_message = AsyncMock(return_value="$event_1")

    web_config = WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )

    auth_manager = AuthManager(
        adapters={"telegram": telegram_adapter, "matrix": matrix_adapter},
        config=web_config,
    )

    ctx = WebContext(
        session_store=AsyncMock(),
        proposal_store=AsyncMock(),
        style_store=AsyncMock(),
        scheduler_store=AsyncMock(),
        trace_store=AsyncMock(),
        failure_store=AsyncMock(),
        app=mock_app,
        auth_manager=auth_manager,
    )
    set_web_context(ctx)

    app = create_web_app()
    app.add_middleware(
        AuthMiddleware,
        auth_manager=auth_manager,
        web_config=web_config,
    )
    return TestClient(app)


class TestAuthFlow:
    """End-to-end auth flow tests."""

    def test_full_flow(self, client: TestClient) -> None:
        # 1. Request a code
        response = client.post("/api/auth/request-code", json={"platform": "telegram"})
        assert response.status_code == 200
        assert response.json()["status"] == "sent"

        # 2. Verify the code
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        auth_manager = ctx.auth_manager
        assert auth_manager is not None
        code = list(auth_manager._pending_codes.keys())[0]

        response = client.post("/api/auth/verify-code", json={"code": code})
        assert response.status_code == 200
        data = response.json()
        token = data["token"]

        # 3. Access a protected endpoint
        response = client.get(
            "/api/sessions", headers={"Authorization": f"Bearer {token}"}
        )
        # 200 or 500 is fine — auth passed, the route itself may fail due to mocks
        assert response.status_code != 401

        # 4. Log out
        response = client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

        # 5. Verify access is denied
        response = client.get(
            "/api/sessions", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_status_reflects_auth_state(self, client: TestClient) -> None:
        # Unauthenticated
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert "available_platforms" in data

        # Authenticate
        response = client.post("/api/auth/request-code", json={"platform": "telegram"})
        assert response.status_code == 200

        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        auth_manager = ctx.auth_manager
        assert auth_manager is not None
        code = list(auth_manager._pending_codes.keys())[0]

        response = client.post("/api/auth/verify-code", json={"code": code})
        assert response.status_code == 200
        token = response.json()["token"]

        # Authenticated
        response = client.get(
            "/api/auth/status", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["platform"] == "telegram"
        assert data["platform_user"] == "12345"

    def test_auth_disabled_allows_all(self, client: TestClient, mock_app: MagicMock) -> None:
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        auth_manager = ctx.auth_manager
        assert auth_manager is not None
        auth_manager.config.auth_enabled = False

        response = client.get("/api/sessions")
        assert response.status_code != 401

        response = client.get("/api/auth/status")
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert response.json()["auth_enabled"] is False
