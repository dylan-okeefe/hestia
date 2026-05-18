"""Unit tests for user and room management API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.config import WebConfig
from hestia.persistence.users import UserStore
from hestia.web.api import create_web_app
from hestia.web.auth import AuthManager, AuthMiddleware, WebSession
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
def user_store() -> MagicMock:
    """Provide a mocked UserStore."""
    return MagicMock(spec=UserStore)


@pytest.fixture
def auth_manager(mock_app: MagicMock, user_store: MagicMock) -> AuthManager:
    """Provide an AuthManager with a user store."""
    web_config = WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )
    return AuthManager(adapters={}, config=web_config, user_store=user_store)


@pytest.fixture
def client(mock_app: MagicMock, auth_manager: AuthManager, user_store: MagicMock) -> TestClient:
    """Create a TestClient with auth middleware and mocked user store."""
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
        auth_manager=auth_manager,
        user_store=user_store,
    )
    set_web_context(ctx)
    app = create_web_app()
    app.add_middleware(
        AuthMiddleware,
        auth_manager=auth_manager,
        web_config=auth_manager.config,
    )
    return TestClient(app)


def _admin_session(auth_manager: AuthManager, user_id: str = "admin-1") -> str:
    """Create and return a token for an admin session."""
    token = "admin_token"
    auth_manager._sessions[token] = WebSession(
        platform="telegram",
        platform_user="admin",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_id=user_id,
    )
    return token


def _user_session(auth_manager: AuthManager, user_id: str = "user-1") -> str:
    """Create and return a token for a regular user session."""
    token = "user_token"
    auth_manager._sessions[token] = WebSession(
        platform="telegram",
        platform_user="user",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_id=user_id,
    )
    return token


from datetime import timedelta


class TestUserRoutes:
    """Tests for /api/users endpoints."""

    def test_list_users(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/users returns all users."""
        token = _user_session(auth_manager)
        user_store.list_users = AsyncMock(
            return_value=[
                MagicMock(
                    id="u1",
                    display_name="Alice",
                    role="admin",
                    trust_preset="household",
                    notes=None,
                    created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
                )
            ]
        )
        user_store.get_identities_for_users = AsyncMock(return_value={"u1": []})
        user_store.get_rooms_for_users = AsyncMock(return_value={"u1": []})

        response = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 1
        assert data["users"][0]["id"] == "u1"
        assert data["users"][0]["display_name"] == "Alice"

    def test_create_user_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """POST /api/users requires admin."""
        response = client.post("/api/users", json={"display_name": "Bob"})
        assert response.status_code == 401

    def test_create_user_non_admin_forbidden(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/users returns 403 for non-admin."""
        token = _user_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="user-1", display_name="User", role="user")
        )

        response = client.post(
            "/api/users",
            json={"display_name": "Bob"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_create_user_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/users creates a user when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.create_user = AsyncMock(
            return_value=MagicMock(
                id="u2",
                display_name="Bob",
                role="user",
                trust_preset=None,
                notes=None,
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )

        response = client.post(
            "/api/users",
            json={"display_name": "Bob", "role": "user"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "u2"
        assert data["display_name"] == "Bob"
        assert data["role"] == "user"

    def test_create_user_child_role(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/users accepts role='child'."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.create_user = AsyncMock(
            return_value=MagicMock(
                id="u-child",
                display_name="Charlie",
                role="child",
                trust_preset=None,
                notes=None,
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )

        response = client.post(
            "/api/users",
            json={"display_name": "Charlie", "role": "child"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "child"

    def test_create_user_invalid_role(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/users returns 422 for invalid role."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )

        response = client.post(
            "/api/users",
            json={"display_name": "Bob", "role": "invalid"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    def test_create_user_invalid_trust_preset(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/users returns 422 for invalid trust_preset."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )

        response = client.post(
            "/api/users",
            json={"display_name": "Bob", "trust_preset": "invalid"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    def test_get_user(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/users/{id} returns user with identities."""
        token = _user_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(
                id="u1",
                display_name="Alice",
                role="admin",
                trust_preset="household",
                notes="test",
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )
        user_store.get_identities = AsyncMock(
            return_value=[
                MagicMock(
                    platform="telegram",
                    platform_user="12345",
                    verified=True,
                )
            ]
        )

        response = client.get("/api/users/u1", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "u1"
        assert data["display_name"] == "Alice"
        assert len(data["identities"]) == 1
        assert data["identities"][0]["platform"] == "telegram"

    def test_get_user_not_found(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/users/{id} returns 404 when missing."""
        token = _user_session(auth_manager)
        user_store.get_user = AsyncMock(return_value=None)

        response = client.get("/api/users/missing", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 404

    def test_update_user_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """PUT /api/users/{id} requires admin."""
        response = client.put("/api/users/u1", json={"display_name": "New"})
        assert response.status_code == 401

    def test_update_user_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """PUT /api/users/{id} updates user when admin."""
        token = _admin_session(auth_manager)

        def _get_user(uid: str):
            if uid == "admin-1":
                return MagicMock(id="admin-1", display_name="Admin", role="admin")
            return MagicMock(id="u1", display_name="Alice", role="user")

        user_store.get_user = AsyncMock(side_effect=_get_user)
        user_store.update_user = AsyncMock(
            return_value=MagicMock(
                id="u1",
                display_name="Alice Updated",
                role="trusted",
                trust_preset="developer",
                notes="notes",
            )
        )

        response = client.put(
            "/api/users/u1",
            json={"display_name": "Alice Updated", "role": "trusted", "trust_preset": "developer", "notes": "notes"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Alice Updated"
        assert data["role"] == "trusted"
        assert data["trust_preset"] == "developer"

    def test_update_user_invalid_role(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """PUT /api/users/{id} returns 422 for invalid role."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )

        response = client.put(
            "/api/users/u1",
            json={"role": "invalid"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422

    def test_delete_user_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """DELETE /api/users/{id} requires admin."""
        response = client.delete("/api/users/u1")
        assert response.status_code == 401

    def test_delete_user_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """DELETE /api/users/{id} deletes user when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.delete_user = AsyncMock(return_value=True)

        response = client.delete(
            "/api/users/u1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    def test_delete_user_not_found(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """DELETE /api/users/{id} returns 404 when missing."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.delete_user = AsyncMock(return_value=False)

        response = client.delete(
            "/api/users/missing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestIdentityRoutes:
    """Tests for /api/users/{id}/identities endpoints."""

    def test_add_identity_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """POST /api/users/{id}/identities requires admin."""
        response = client.post(
            "/api/users/u1/identities",
            json={"platform": "telegram", "platform_user": "12345"},
        )
        assert response.status_code == 401

    def test_add_identity_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/users/{id}/identities adds identity when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.add_identity = AsyncMock(return_value=None)

        response = client.post(
            "/api/users/u1/identities",
            json={"platform": "telegram", "platform_user": "12345"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["added"] is True
        user_store.add_identity.assert_awaited_once_with("u1", "telegram", "12345")

    def test_remove_identity_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """DELETE /api/users/{id}/identities/{platform}/{platform_user} requires admin."""
        response = client.delete("/api/users/u1/identities/telegram/12345")
        assert response.status_code == 401

    def test_remove_identity_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """DELETE identity removes it when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.remove_identity = AsyncMock(return_value=True)

        response = client.delete(
            "/api/users/u1/identities/telegram/12345",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["removed"] is True
        user_store.remove_identity.assert_awaited_once_with("telegram", "12345")


class TestHandoffRoutes:
    """Tests for /api/users/{id}/handoffs endpoint."""

    def test_get_user_handoffs(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """GET /api/users/{id}/handoffs returns handoffs for the user's identities."""
        from unittest.mock import AsyncMock

        token = _user_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(
                id="user-1", display_name="Alice", role="user"
            )
        )
        user_store.get_identities = AsyncMock(
            return_value=[
                MagicMock(platform="telegram", platform_user="12345"),
            ]
        )

        # Replace session_store with one that returns handoffs
        handoffs = [
            {
                "session_id": "sess_1",
                "summary": "User asked about weather...",
                "created_at": "2026-05-10T14:00:00+00:00",
            },
            {
                "session_id": "sess_2",
                "summary": "Discussed project planning",
                "created_at": "2026-05-09T10:00:00+00:00",
            },
        ]
        session_store = AsyncMock()
        session_store.list_handoffs_for_identities = AsyncMock(return_value=handoffs)

        ctx = WebContext(
            session_store=session_store,
            proposal_store=AsyncMock(),
            style_store=AsyncMock(),
            scheduler_store=AsyncMock(),
            trace_store=AsyncMock(),
            failure_store=AsyncMock(),
            workflow_store=AsyncMock(),
            execution_store=AsyncMock(),
            app=MagicMock(),
            auth_manager=auth_manager,
            user_store=user_store,
        )
        set_web_context(ctx)

        response = client.get(
            "/api/users/user-1/handoffs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["session_id"] == "sess_1"
        assert data[0]["summary"] == "User asked about weather..."
        session_store.list_handoffs_for_identities.assert_awaited_once_with(
            [("telegram", "12345")], limit=3
        )

    def test_get_user_handoffs_not_found(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """GET /api/users/{id}/handoffs returns 404 for missing user."""
        token = _user_session(auth_manager)
        user_store.get_user = AsyncMock(return_value=None)

        response = client.get(
            "/api/users/missing/handoffs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestRoomRoutes:
    """Tests for /api/rooms endpoints."""

    def test_list_rooms(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/rooms returns all rooms."""
        token = _user_session(auth_manager)
        user_store.list_rooms = AsyncMock(
            return_value=[
                MagicMock(
                    id="r1",
                    platform="telegram",
                    platform_room_id="-12345",
                    display_name="General",
                    created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
                )
            ]
        )

        response = client.get("/api/rooms", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["rooms"]) == 1
        assert data["rooms"][0]["id"] == "r1"

    def test_get_room(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/rooms/{id} returns room with members."""
        token = _user_session(auth_manager)
        user_store.get_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                platform="telegram",
                platform_room_id="-12345",
                display_name="General",
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )
        user_store.get_room_members = AsyncMock(
            return_value=[
                MagicMock(id="u1", display_name="Alice", role="admin")
            ]
        )

        response = client.get("/api/rooms/r1", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "r1"
        assert len(data["members"]) == 1
        assert data["members"][0]["display_name"] == "Alice"

    def test_get_room_not_found(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/rooms/{id} returns 404 when missing."""
        token = _user_session(auth_manager)
        user_store.get_room = AsyncMock(return_value=None)

        response = client.get("/api/rooms/missing", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 404

    def test_update_room_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """PUT /api/rooms/{id} requires admin."""
        response = client.put("/api/rooms/r1", json={"display_name": "New"})
        assert response.status_code == 401

    def test_update_room_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """PUT /api/rooms/{id} updates room when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.get_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                platform="telegram",
                platform_room_id="-12345",
                display_name="General",
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )
        user_store.update_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                display_name="Updated",
            )
        )

        response = client.put(
            "/api/rooms/r1",
            json={"display_name": "Updated"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Updated"

    def test_list_room_members(self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock) -> None:
        """GET /api/rooms/{id}/members returns members."""
        token = _user_session(auth_manager)
        user_store.get_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                platform="telegram",
                platform_room_id="-12345",
                display_name="General",
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )
        user_store.get_room_members = AsyncMock(
            return_value=[
                MagicMock(id="u1", display_name="Alice", role="admin")
            ]
        )

        response = client.get("/api/rooms/r1/members", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["members"]) == 1

    def test_add_room_member_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """POST /api/rooms/{id}/members requires admin."""
        response = client.post("/api/rooms/r1/members", json={"user_id": "u1"})
        assert response.status_code == 401

    def test_add_room_member_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """POST /api/rooms/{id}/members adds member when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.add_room_member = AsyncMock(return_value=None)

        response = client.post(
            "/api/rooms/r1/members",
            json={"user_id": "u1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["added"] is True
        user_store.add_room_member.assert_awaited_once_with("r1", "u1")

    def test_remove_room_member_admin_required(
        self, client: TestClient, auth_manager: AuthManager
    ) -> None:
        """DELETE /api/rooms/{id}/members/{user_id} requires admin."""
        response = client.delete("/api/rooms/r1/members/u1")
        assert response.status_code == 401

    def test_remove_room_member_success(
        self, client: TestClient, auth_manager: AuthManager, user_store: MagicMock
    ) -> None:
        """DELETE member removes it when admin."""
        token = _admin_session(auth_manager)
        user_store.get_user = AsyncMock(
            return_value=MagicMock(id="admin-1", display_name="Admin", role="admin")
        )
        user_store.remove_room_member = AsyncMock(return_value=True)

        response = client.delete(
            "/api/rooms/r1/members/u1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["removed"] is True
