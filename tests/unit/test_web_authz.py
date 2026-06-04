"""Authorization and validation tests for dashboard API routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.config import WebConfig
from hestia.web.api import create_web_app
from hestia.web.auth import AuthMiddleware, WebSession
from hestia.web.context import WebContext, set_web_context


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
def auth_client(mock_app: MagicMock) -> TestClient:
    """Create a TestClient with auth enabled and multiple user tokens."""
    web_config = WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )
    auth_manager = MagicMock()
    auth_manager.config = web_config
    auth_manager.validate_token = MagicMock(return_value=("missing", None))

    now = datetime.now(UTC)
    expires = now + timedelta(hours=1)

    # Register tokens for different users
    sessions = {
        "token_user_a": WebSession(
            platform="cli",
            platform_user="user_a",
            created_at=now,
            expires_at=expires,
            user_id="user-a-id",
        ),
        "token_user_b": WebSession(
            platform="cli",
            platform_user="user_b",
            created_at=now,
            expires_at=expires,
            user_id="user-b-id",
        ),
        "token_admin": WebSession(
            platform="cli",
            platform_user="admin",
            created_at=now,
            expires_at=expires,
            user_id="admin-id",
        ),
    }

    def _validate(token: str) -> tuple[str, WebSession | None]:
        session = sessions.get(token)
        if session is not None:
            return ("valid", session)
        return ("missing", None)

    auth_manager.validate_token = _validate

    user_store = AsyncMock()
    user_store.get_user = AsyncMock(
        side_effect=lambda uid: MagicMock(
            role="admin" if uid == "admin-id" else "user"
        )
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


class TestSessionsAuth:
    """Authorization tests for /api/sessions endpoints."""

    def test_list_sessions_filters_to_caller(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Only the caller's sessions are returned."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.list_sessions = AsyncMock(
            return_value=[
                MagicMock(
                    id="s1",
                    platform="cli",
                    platform_user="user_a",
                    started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
                    last_active_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
                    state=MagicMock(value="ACTIVE"),
                    temperature=MagicMock(value="COLD"),
                )
            ]
        )
        ctx.session_store.count_turns_for_sessions = AsyncMock(return_value={})

        response = auth_client.get(
            "/api/sessions",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["platform_user"] == "user_a"
        ctx.session_store.list_sessions.assert_awaited_once_with(
            limit=50, platform=None, platform_user="user_a"
        )

    def test_get_session_messages_for_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing another user's session messages returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.get_session = AsyncMock(
            return_value=MagicMock(
                id="s1",
                platform="cli",
                platform_user="user_b",
                started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        )

        response = auth_client.get(
            "/api/sessions/s1/messages",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403


class TestMemoryAuth:
    """Authorization tests for /api/memory endpoints."""

    def test_delete_other_user_memory_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Deleting another user's memory returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.app.memory_store.get = AsyncMock(
            return_value=MagicMock(
                id="mem1",
                content="secret",
                platform_user="user_b",
            )
        )

        response = auth_client.delete(
            "/api/memory/mem1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403


class TestSchedulerAuth:
    """Authorization and validation tests for /api/scheduler endpoints."""

    def test_create_task_uses_caller_platform_user(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Task session_id is derived from the authenticated platform_user."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.scheduler_store.create_task = AsyncMock(
            return_value=MagicMock(
                id="task_new",
                session_id="user_a",
                prompt="test prompt",
                description=None,
                cron_expression="0 8 * * *",
                enabled=True,
                notify=False,
                created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
                next_run_at=datetime(2024, 1, 2, 8, 0, 0, tzinfo=UTC),
            )
        )

        response = auth_client.post(
            "/api/scheduler/tasks",
            json={"prompt": "test prompt", "cron_expression": "0 8 * * *"},
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200
        ctx.scheduler_store.create_task.assert_awaited_once()
        call_kwargs = ctx.scheduler_store.create_task.await_args.kwargs
        assert call_kwargs["session_id"] == "user_a"

    def test_update_other_user_task_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Updating another user's task returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.scheduler_store.get_task = AsyncMock(
            return_value=MagicMock(
                id="task1",
                session_id="user_b",
                prompt="hello",
            )
        )

        response = auth_client.put(
            "/api/scheduler/tasks/task1",
            json={"prompt": "hacked"},
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_create_task_with_invalid_cron_returns_422(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """POST task with invalid cron expression returns 422."""
        response = auth_client.post(
            "/api/scheduler/tasks",
            json={"prompt": "test", "cron_expression": "not-a-cron"},
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 422


class TestErrorsAuth:
    """Authorization tests for /api/errors endpoints."""

    def test_list_errors_non_admin_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users cannot access the errors dashboard."""
        response = auth_client.get(
            "/api/errors",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403


class TestTracesAuth:
    """Authorization tests for /api/traces and /api/failures endpoints."""

    def test_list_traces_no_auth_returns_401(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Unauthenticated requests to /traces return 401."""
        response = auth_client.get("/api/traces")
        assert response.status_code == 401

    def test_list_traces_with_session_id_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing traces for another user's session returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.get_session = AsyncMock(
            return_value=MagicMock(
                id="s1",
                platform="cli",
                platform_user="user_b",
            )
        )

        response = auth_client.get(
            "/api/traces?session_id=s1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_list_traces_with_session_id_owner_returns_200(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing traces for the caller's own session returns 200."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.get_session = AsyncMock(
            return_value=MagicMock(
                id="s1",
                platform="cli",
                platform_user="user_a",
            )
        )
        ctx.trace_store.list_recent = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/traces?session_id=s1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_list_traces_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access all traces."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.trace_store.list_recent = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/traces",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200

    def test_list_failures_no_auth_returns_401(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Unauthenticated requests to /failures return 401."""
        response = auth_client.get("/api/failures")
        assert response.status_code == 401

    def test_list_failures_with_session_id_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing failures for another user's session returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.get_session = AsyncMock(
            return_value=MagicMock(
                id="s1",
                platform="cli",
                platform_user="user_b",
            )
        )

        response = auth_client.get(
            "/api/failures?session_id=s1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_list_failures_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access all failures."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.failure_store.list_recent = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/failures",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200


class TestStyleAuth:
    """Authorization tests for /api/style endpoints."""

    def test_get_style_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing another user's style profile returns 403."""
        response = auth_client.get(
            "/api/style/cli/user_b",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_get_style_owner_returns_200(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing the caller's own style profile returns 200."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.style_store.get_profile_dict = AsyncMock(return_value={})

        response = auth_client.get(
            "/api/style/cli/user_a",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_delete_style_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Deleting another user's style metric returns 403."""
        response = auth_client.delete(
            "/api/style/cli/user_b/metric",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_style_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access any style profile."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.style_store.get_profile_dict = AsyncMock(return_value={})

        response = auth_client.get(
            "/api/style/cli/user_b",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200


class TestEgressAuth:
    """Authorization tests for /api/egress endpoints."""

    def test_list_egress_no_auth_returns_401(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Unauthenticated requests to /egress return 401."""
        response = auth_client.get("/api/egress")
        assert response.status_code == 401

    def test_list_egress_owner_returns_200(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Authenticated user can access their own egress."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.list_sessions = AsyncMock(return_value=[])
        ctx.trace_store.list_egress = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/egress",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_list_egress_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access all egress."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.trace_store.list_egress = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/egress",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200


class TestUsersAuth:
    """Authorization tests for /api/users and /api/rooms endpoints."""

    def test_list_users_non_admin_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users cannot list all users."""
        response = auth_client.get(
            "/api/users",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_list_users_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can list all users."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.list_users = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200

    def test_get_user_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing another user's profile returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user = AsyncMock(
            side_effect=lambda uid: MagicMock(
                id=uid,
                role="admin" if uid == "admin-id" else "user",
            )
        )
        ctx.user_store.get_identities = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users/user-b-id",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_get_user_owner_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Users can access their own profile."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user = AsyncMock(
            side_effect=lambda uid: MagicMock(
                id=uid,
                role="admin" if uid == "admin-id" else "user",
            )
        )
        ctx.user_store.get_identities = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users/user-a-id",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_get_user_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access any user profile."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user = AsyncMock(
            side_effect=lambda uid: MagicMock(
                id=uid,
                role="admin" if uid == "admin-id" else "user",
            )
        )
        ctx.user_store.get_identities = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users/user-b-id",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200

    def test_get_handoffs_other_user_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing another user's handoffs returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user = AsyncMock(
            side_effect=lambda uid: MagicMock(
                id=uid,
                role="admin" if uid == "admin-id" else "user",
            )
        )
        ctx.user_store.get_identities = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users/user-b-id/handoffs",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_get_handoffs_owner_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Users can access their own handoffs."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user = AsyncMock(
            side_effect=lambda uid: MagicMock(
                id=uid,
                role="admin" if uid == "admin-id" else "user",
            )
        )
        ctx.user_store.get_identities = AsyncMock(return_value=[])
        ctx.session_store.list_handoffs_for_identities = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users/user-a-id/handoffs",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_get_handoffs_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access any user's handoffs."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user = AsyncMock(
            side_effect=lambda uid: MagicMock(
                id=uid,
                role="admin" if uid == "admin-id" else "user",
            )
        )
        ctx.user_store.get_identities = AsyncMock(return_value=[])
        ctx.session_store.list_handoffs_for_identities = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/users/user-b-id/handoffs",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200

    def test_list_rooms_non_admin_filters_to_own(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users see only their own rooms."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_user_rooms = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/rooms",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_get_room_non_member_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-members cannot access a room."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                platform="cli",
                platform_room_id="room1",
                display_name="Room 1",
            )
        )
        ctx.user_store.get_room_members = AsyncMock(
            return_value=[MagicMock(id="user-b-id")]
        )

        response = auth_client.get(
            "/api/rooms/r1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_get_room_member_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Room members can access a room."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                platform="cli",
                platform_room_id="room1",
                display_name="Room 1",
            )
        )
        ctx.user_store.get_room_members = AsyncMock(
            return_value=[MagicMock(id="user-a-id")]
        )

        response = auth_client.get(
            "/api/rooms/r1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 200

    def test_list_room_members_non_member_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-members cannot list room members."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.user_store.get_room = AsyncMock(
            return_value=MagicMock(
                id="r1",
                platform="cli",
                platform_room_id="room1",
                display_name="Room 1",
            )
        )
        ctx.user_store.get_room_members = AsyncMock(
            return_value=[MagicMock(id="user-b-id")]
        )

        response = auth_client.get(
            "/api/rooms/r1/members",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403


class TestProposalsAuth:
    """Authorization tests for /api/proposals endpoints."""

    def test_list_proposals_non_admin_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users cannot list proposals."""
        response = auth_client.get(
            "/api/proposals",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_accept_proposal_non_admin_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users cannot accept proposals."""
        response = auth_client.post(
            "/api/proposals/p1/accept",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_reject_proposal_non_admin_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users cannot reject proposals."""
        response = auth_client.post(
            "/api/proposals/p1/reject",
            json={"note": ""},
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_defer_proposal_non_admin_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Non-admin users cannot defer proposals."""
        response = auth_client.post(
            "/api/proposals/p1/defer",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_proposals_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access proposals."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.proposal_store.list_by_status = AsyncMock(return_value=[])

        response = auth_client.get(
            "/api/proposals",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200


class TestRequireOwnerFailOpen:
    """Tests for the H5 fail-open RequireOwner fix."""

    def test_require_owner_raises_401_when_auth_enabled_and_no_platform_user(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """RequireOwner raises 401 when auth is enabled and platform_user is missing."""
        response = auth_client.get("/api/style/cli/someuser")
        assert response.status_code == 401


class TestWorkflowsAuth:
    """Authorization tests for /api/workflows endpoints."""

    def test_get_workflow_other_owner_returns_403(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Accessing another user's workflow returns 403."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.get_workflow = AsyncMock(
            return_value=MagicMock(
                id="wf1",
                name="Workflow 1",
                trigger_type="manual",
                trigger_config={},
                owner_id="user_b",
                trust_level="paranoid",
            )
        )

        response = auth_client.get(
            "/api/workflows/wf1",
            headers={"Authorization": "Bearer token_user_a"},
        )
        assert response.status_code == 403

    def test_get_workflow_admin_can_access(
        self, auth_client: TestClient, mock_app: MagicMock
    ) -> None:
        """Admin can access any workflow."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.workflow_store.get_workflow = AsyncMock(
            return_value=MagicMock(
                id="wf1",
                name="Workflow 1",
                trigger_type="manual",
                trigger_config={},
                owner_id="user_b",
                trust_level="paranoid",
            )
        )
        ctx.workflow_store.get_active_version = AsyncMock(return_value=None)

        response = auth_client.get(
            "/api/workflows/wf1",
            headers={"Authorization": "Bearer token_admin"},
        )
        assert response.status_code == 200
