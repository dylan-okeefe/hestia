"""Unit tests for browser stream WebSocket auth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hestia.config import WebConfig
from hestia.persistence.users import User
from hestia.web.api import create_web_app
from hestia.web.auth import AuthManager, WebSession
from hestia.web.browser_stream import SessionStreamManager
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
    mock.event_bus = AsyncMock()
    return mock


@pytest.fixture
def auth_manager() -> AuthManager:
    """Provide an AuthManager with a real WebConfig."""
    return AuthManager(adapters={}, config=WebConfig(auth_enabled=True), user_store=None)


@pytest.fixture
def stream_manager() -> MagicMock:
    """Provide a mocked active SessionStreamManager."""
    manager = MagicMock(spec=SessionStreamManager)
    manager.is_active.return_value = True
    manager.get_session_id.return_value = "test-session"
    manager._session = MagicMock()
    manager._session.ws_clients = set()
    return manager


@pytest.fixture
def ws_ctx(
    mock_app: MagicMock,
    auth_manager: AuthManager,
    stream_manager: MagicMock,
) -> tuple[TestClient, WebContext]:
    """Create a TestClient and WebContext for WebSocket tests."""
    user_store = AsyncMock()
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
        stream_manager=stream_manager,
    )
    set_web_context(ctx)
    app = create_web_app()
    client = TestClient(app)
    return client, ctx


def _make_token(auth_manager: AuthManager, user_id: str | None) -> str:
    """Inject a session token and return it."""
    token = f"token-{user_id or 'none'}"
    now = datetime.now(UTC)
    session = WebSession(
        platform="telegram",
        platform_user="testuser",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        user_id=user_id,
    )
    auth_manager._sessions[token] = session
    return token


def _make_user(user_id: str, role: str) -> User:
    """Return a User instance for mocking."""
    now = datetime.now(UTC)
    return User(
        id=user_id,
        display_name="Test User",
        role=role,
        trust_preset=None,
        notes=None,
        created_at=now,
        updated_at=now,
    )


class TestBrowserStreamWSAuth:
    """Auth gate tests for /api/browser-session/stream/{session_id}."""

    def test_valid_token_no_user_id_is_rejected(
        self,
        ws_ctx: tuple[TestClient, WebContext],
        auth_manager: AuthManager,
    ) -> None:
        """A valid OTP with no registry mapping must be rejected."""
        client, _ctx = ws_ctx
        token = _make_token(auth_manager, user_id=None)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/api/browser-session/stream/test-session?token={token}"
            ):
                pass  # pragma: no cover

        assert exc_info.value.code == 1008

    def test_valid_token_non_admin_is_rejected(
        self,
        ws_ctx: tuple[TestClient, WebContext],
        auth_manager: AuthManager,
    ) -> None:
        """A valid session linked to a non-admin user must be rejected."""
        client, ctx = ws_ctx
        ctx.user_store.get_user = AsyncMock(return_value=_make_user("u1", "user"))
        token = _make_token(auth_manager, user_id="u1")

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/api/browser-session/stream/test-session?token={token}"
            ):
                pass  # pragma: no cover

        assert exc_info.value.code == 1008
        ctx.user_store.get_user.assert_awaited_once_with("u1")

    def test_admin_token_is_accepted(
        self,
        ws_ctx: tuple[TestClient, WebContext],
        auth_manager: AuthManager,
        stream_manager: MagicMock,
    ) -> None:
        """A valid session linked to an admin user may connect."""
        client, ctx = ws_ctx
        ctx.user_store.get_user = AsyncMock(return_value=_make_user("u1", "admin"))
        token = _make_token(auth_manager, user_id="u1")

        with client.websocket_connect(
            f"/api/browser-session/stream/test-session?token={token}"
        ):
            # Connection accepted; the route adds the socket to the client set.
            assert len(stream_manager._session.ws_clients) == 1

        ctx.user_store.get_user.assert_awaited_once_with("u1")
