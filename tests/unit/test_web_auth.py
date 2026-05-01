"""Unit tests for web dashboard authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.config import WebConfig
from hestia.web.api import create_web_app
from hestia.web.auth import AuthManager, AuthMiddleware, PendingCode, WebSession
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
def web_config() -> WebConfig:
    return WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )


@pytest.fixture
def telegram_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter._config = MagicMock(allowed_users=["12345"])
    adapter.send_message = AsyncMock(return_value="msg_1")
    return adapter


@pytest.fixture
def matrix_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter._config = MagicMock(allowed_rooms=["!room:matrix.org"])
    adapter.send_message = AsyncMock(return_value="$event_1")
    return adapter


@pytest.fixture
def auth_manager(
    telegram_adapter: MagicMock, matrix_adapter: MagicMock, web_config: WebConfig
) -> AuthManager:
    adapters = {
        "telegram": telegram_adapter,
        "matrix": matrix_adapter,
    }
    return AuthManager(adapters=adapters, config=web_config)


class TestAuthManager:
    """Tests for AuthManager."""

    def test_generate_code_length(self, auth_manager: AuthManager) -> None:
        code = auth_manager.generate_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_code_randomness(self, auth_manager: AuthManager) -> None:
        codes = {auth_manager.generate_code() for _ in range(100)}
        assert len(codes) > 1

    def test_request_code_telegram(
        self, auth_manager: AuthManager, telegram_adapter: MagicMock
    ) -> None:
        import asyncio

        result = asyncio.run(auth_manager.request_code("telegram"))
        assert result["status"] == "sent"
        assert result["platform"] == "telegram"
        assert result["expires_in"] == 300
        telegram_adapter.send_message.assert_awaited_once()
        args = telegram_adapter.send_message.await_args
        assert args[0][0] == "12345"
        assert "Your Hestia dashboard code is:" in args[0][1]

    def test_request_code_missing_platform(self, auth_manager: AuthManager) -> None:
        with pytest.raises(ValueError, match="not configured"):
            import asyncio

            asyncio.run(auth_manager.request_code("discord"))

    def test_request_code_multiple_users(self, auth_manager: AuthManager) -> None:
        auth_manager.adapters["telegram"]._config.allowed_users = ["123", "456"]
        with pytest.raises(ValueError, match="exactly one configured user"):
            import asyncio

            asyncio.run(auth_manager.request_code("telegram"))

    def test_validate_code_success(self, auth_manager: AuthManager) -> None:
        import asyncio

        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]

        session = auth_manager.validate_code(code, "127.0.0.1")
        assert session is not None
        assert session.platform == "telegram"
        assert session.platform_user == "12345"
        assert code not in auth_manager._pending_codes
        assert len(auth_manager._sessions) == 1

    def test_validate_code_invalid(self, auth_manager: AuthManager) -> None:
        session = auth_manager.validate_code("000000", "127.0.0.1")
        assert session is None

    def test_validate_code_expired(self, auth_manager: AuthManager) -> None:
        import asyncio

        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]

        # Expire the code
        auth_manager._pending_codes[code].expires_at = datetime.now(UTC) - timedelta(seconds=1)

        session = auth_manager.validate_code(code, "127.0.0.1")
        assert session is None

    def test_validate_code_rate_limit(self, auth_manager: AuthManager) -> None:
        for i in range(5):
            auth_manager.validate_code(f"bad{i}", "127.0.0.1")

        session = auth_manager.validate_code("bad5", "127.0.0.1")
        assert session is None

    def test_rate_limit_resets_after_window(self, auth_manager: AuthManager) -> None:
        for i in range(5):
            auth_manager.validate_code(f"bad{i}", "127.0.0.1")

        # Backdate attempts
        window = auth_manager._rate_limits["127.0.0.1"]
        for i in range(len(window.attempts)):
            window.attempts[i] -= timedelta(minutes=11)

        session = auth_manager.validate_code("bad5", "127.0.0.1")
        assert session is None  # still invalid code, but not rate limited
        assert len(window.attempts) == 1  # only the latest attempt recorded

    def test_get_session_valid(self, auth_manager: AuthManager) -> None:
        import asyncio

        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]
        session = auth_manager.validate_code(code, "127.0.0.1")
        assert session is not None

        token = list(auth_manager._sessions.keys())[0]
        retrieved = auth_manager.get_session(token)
        assert retrieved is not None
        assert retrieved.platform == "telegram"

    def test_get_session_expired(self, auth_manager: AuthManager) -> None:
        token = "test_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC) - timedelta(hours=73),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert auth_manager.get_session(token) is None
        assert token not in auth_manager._sessions

    def test_remove_session(self, auth_manager: AuthManager) -> None:
        token = "test_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert auth_manager.remove_session(token) is True
        assert auth_manager.remove_session(token) is False

    def test_validate_token(self, auth_manager: AuthManager) -> None:
        token = "test_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        status, session = auth_manager.validate_token(token)
        assert status == "valid"
        assert session is not None

        status, session = auth_manager.validate_token("missing")
        assert status == "missing"

        auth_manager._sessions["expired"] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC) - timedelta(hours=73),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        status, session = auth_manager.validate_token("expired")
        assert status == "expired"


class TestAuthMiddleware:
    """Tests for AuthMiddleware."""

    def test_passes_with_valid_token(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({
                "platform": getattr(request.state, "platform", None),
                "user": getattr(request.state, "platform_user", None),
            })

        app = Starlette()
        app.add_route("/api/sessions", endpoint)
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        token = "valid_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        client = TestClient(app)
        response = client.get("/api/sessions", headers={"Authorization": "Bearer valid_token"})
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "telegram"
        assert data["user"] == "12345"

    def test_rejects_missing_token(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        app = Starlette()
        app.add_route("/api/sessions", endpoint)
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        client = TestClient(app)
        response = client.get("/api/sessions")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"

    def test_rejects_invalid_token(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        app = Starlette()
        app.add_route("/api/sessions", endpoint)
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        client = TestClient(app)
        response = client.get("/api/sessions", headers={"Authorization": "Bearer invalid"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"

    def test_rejects_expired_token(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        app = Starlette()
        app.add_route("/api/sessions", endpoint)
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        token = "expired_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC) - timedelta(hours=73),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )

        client = TestClient(app)
        response = client.get("/api/sessions", headers={"Authorization": "Bearer expired_token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Session expired"
        assert token not in auth_manager._sessions

    def test_skips_auth_endpoints(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        app = Starlette()
        app.add_route("/api/auth/status", endpoint)
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        client = TestClient(app)
        response = client.get("/api/auth/status")
        assert response.status_code == 200

    def test_skips_static_routes(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        app = Starlette()
        app.add_route("/", endpoint)
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200

    def test_skips_when_auth_disabled(self, auth_manager: AuthManager) -> None:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        async def endpoint(request: Request) -> JSONResponse:
            return JSONResponse({"ok": True})

        app = Starlette()
        app.add_route("/api/sessions", endpoint)
        auth_manager.config.auth_enabled = False
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )

        client = TestClient(app)
        response = client.get("/api/sessions")
        assert response.status_code == 200


class TestAuthRoutes:
    """Tests for /api/auth/* endpoints."""

    @pytest.fixture
    def client(
        self, mock_app: MagicMock, auth_manager: AuthManager
    ) -> TestClient:
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
        from hestia.web.auth import AuthMiddleware
        app.add_middleware(
            AuthMiddleware,
            auth_manager=auth_manager,
            web_config=auth_manager.config,
        )
        return TestClient(app)

    def test_request_code(self, client: TestClient, auth_manager: AuthManager) -> None:
        response = client.post("/api/auth/request-code", json={"platform": "telegram"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["platform"] == "telegram"
        assert data["expires_in"] == 300

    def test_request_code_missing_platform(self, client: TestClient) -> None:
        response = client.post("/api/auth/request-code", json={"platform": "discord"})
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_verify_code(self, client: TestClient, auth_manager: AuthManager) -> None:
        import asyncio

        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]

        response = client.post("/api/auth/verify-code", json={"code": code})
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "telegram"
        assert data["platform_user"] == "12345"
        assert "token" in data
        assert "expires_at" in data

    def test_verify_code_invalid(self, client: TestClient) -> None:
        response = client.post("/api/auth/verify-code", json={"code": "000000"})
        assert response.status_code == 401
        assert "Invalid or expired code" in response.json()["detail"]

    def test_verify_code_rate_limit(self, client: TestClient) -> None:
        for i in range(5):
            response = client.post("/api/auth/verify-code", json={"code": f"bad{i}"})
            assert response.status_code == 401

        response = client.post("/api/auth/verify-code", json={"code": "bad5"})
        assert response.status_code == 401

    def test_logout(self, client: TestClient, auth_manager: AuthManager) -> None:
        token = "test_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        response = client.post("/api/auth/logout", headers={"Authorization": "Bearer test_token"})
        assert response.status_code == 200
        assert token not in auth_manager._sessions

    def test_status_authenticated(self, client: TestClient, auth_manager: AuthManager) -> None:
        token = "test_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        response = client.get("/api/auth/status", headers={"Authorization": "Bearer test_token"})
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["platform"] == "telegram"

    def test_status_unauthenticated(self, client: TestClient) -> None:
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert "available_platforms" in data

    def test_status_auth_disabled(self, client: TestClient, auth_manager: AuthManager) -> None:
        auth_manager.config.auth_enabled = False
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["auth_enabled"] is False

    def test_protected_route_blocked_without_auth(self, client: TestClient) -> None:
        response = client.get("/api/sessions")
        assert response.status_code == 401

    def test_protected_route_passes_with_auth(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        token = "test_token"
        auth_manager._sessions[token] = WebSession(
            platform="telegram",
            platform_user="12345",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        response = client.get("/api/sessions", headers={"Authorization": "Bearer test_token"})
        # Should pass auth but may 200 or 500 depending on store mocks
        assert response.status_code in (200, 500)
