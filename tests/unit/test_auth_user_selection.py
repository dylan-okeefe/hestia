"""Unit tests for auth user-selection features."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.config import WebConfig
from hestia.persistence.users import UserStore
from hestia.web.api import create_web_app
from hestia.web.auth import AuthManager, AuthMiddleware
from hestia.web.context import WebContext, set_web_context


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
    mock.config.matrix = MagicMock(
        homeserver="", user_id="", access_token="", allowed_rooms=[]
    )
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
    return mock


@pytest.fixture
def telegram_adapter() -> MagicMock:
    """Provide a mocked Telegram adapter."""
    adapter = MagicMock()
    adapter._config = MagicMock(allowed_users=["12345", "67890"])
    adapter.send_message = AsyncMock(return_value="msg_1")
    return adapter


@pytest.fixture
def user_store() -> MagicMock:
    """Provide a mocked UserStore."""
    return MagicMock(spec=UserStore)


@pytest.fixture
def client(
    mock_app: MagicMock,
    telegram_adapter: MagicMock,
    user_store: MagicMock,
) -> TestClient:
    """Create a TestClient with auth middleware and user store."""
    web_config = WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )
    auth_manager = AuthManager(
        adapters={"telegram": telegram_adapter},
        config=web_config,
        user_store=user_store,
    )

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
        auth_manager=auth_manager,
        user_store=user_store,
    )
    set_web_context(ctx)

    app = create_web_app()
    app.add_middleware(
        AuthMiddleware,
        auth_manager=auth_manager,
        web_config=web_config,
    )
    return TestClient(app)


class TestAvailableUsers:
    """Tests for GET /api/auth/available-users."""

    def test_available_users_returns_users(
        self, client: TestClient, user_store: MagicMock
    ) -> None:
        """SEC-004: the unauthenticated picker endpoint returns only ids and
        display names — no roles, platforms, or identity bindings."""
        user_store.list_users = AsyncMock(
            return_value=[
                MagicMock(id="u1", display_name="Alice", role="admin"),
                MagicMock(id="u2", display_name="Bob", role="user"),
            ]
        )
        user_store.get_identities = AsyncMock(
            side_effect=[
                [MagicMock(platform="telegram", platform_user="12345")],
                [
                    MagicMock(platform="matrix", platform_user="!room:example.com"),
                    MagicMock(platform="telegram", platform_user="67890"),
                ],
            ]
        )

        response = client.get("/api/auth/available-users")
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 2
        assert data["users"][0] == {"user_id": "u1", "display_name": "Alice"}
        assert data["users"][1] == {"user_id": "u2", "display_name": "Bob"}
        assert "role" not in data["users"][0]
        assert "identities" not in data["users"][0]
        assert "platforms" not in data["users"][0]

        # Identity lookups are no longer needed for this endpoint.
        user_store.get_identities.assert_not_called()

    def test_available_users_empty_when_no_store(
        self, client: TestClient, user_store: MagicMock
    ) -> None:
        """GET /api/auth/available-users returns empty when user_store is None."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.auth_manager._user_store = None

        response = client.get("/api/auth/available-users")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == []


class TestRequestCodeWithPlatformUser:
    """Tests for POST /api/auth/request-code with explicit platform_user."""

    def test_request_code_with_platform_user(
        self, client: TestClient, telegram_adapter: MagicMock
    ) -> None:
        """SEC-002: explicit platform_user is honored when allowlisted."""
        response = client.post(
            "/api/auth/request-code",
            json={"platform": "telegram", "platform_user": "67890"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"

        # Verify send_message was called with the explicit platform_user
        telegram_adapter.send_message.assert_awaited_once()
        args = telegram_adapter.send_message.await_args
        assert args[0][0] == "67890"
        assert "Your Hestia dashboard code is:" in args[0][1]

    def test_request_code_without_platform_user_fallback(
        self, client: TestClient, telegram_adapter: MagicMock
    ) -> None:
        """POST /api/auth/request-code falls back to first configured user."""
        response = client.post(
            "/api/auth/request-code",
            json={"platform": "telegram"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"

        # Verify send_message was called with the first configured user
        telegram_adapter.send_message.assert_awaited_once()
        args = telegram_adapter.send_message.await_args
        assert args[0][0] == "12345"


class TestVerifyCodeResolvesUserId:
    """Tests for user_id resolution during code verification."""

    def test_verify_code_sets_user_id(
        self, client: TestClient, user_store: MagicMock
    ) -> None:
        """POST /api/auth/verify-code resolves user_id from identity."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        auth_manager = ctx.auth_manager
        assert auth_manager is not None

        # Request a code
        import asyncio

        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]

        # Mock user lookup
        user_store.get_user_by_identity = AsyncMock(
            return_value=MagicMock(id="user-123")
        )

        response = client.post("/api/auth/verify-code", json={"code": code})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data

        # Verify the session has user_id
        token = data["token"]
        session = auth_manager.get_session(token)
        assert session is not None
        assert session.user_id == "user-123"
        user_store.get_user_by_identity.assert_awaited_once_with("telegram", "12345")

    def test_verify_code_no_user_id_when_no_identity(
        self, client: TestClient, user_store: MagicMock
    ) -> None:
        """POST /api/auth/verify-code sets user_id to None when identity not found."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        auth_manager = ctx.auth_manager
        assert auth_manager is not None

        import asyncio

        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]

        user_store.get_user_by_identity = AsyncMock(return_value=None)

        response = client.post("/api/auth/verify-code", json={"code": code})
        assert response.status_code == 200
        data = response.json()
        token = data["token"]

        session = auth_manager.get_session(token)
        assert session is not None
        assert session.user_id is None
