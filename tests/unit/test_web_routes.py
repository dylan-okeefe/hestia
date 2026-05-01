"""Unit tests for dashboard API routes with mocked stores."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.web.api import create_web_app
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
    mock.config.features.web = MagicMock(enabled=True, host="127.0.0.1", port=8080, auth_enabled=False, session_lifetime_hours=72, code_expiry_seconds=300, code_length=6)
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
        app=mock_app,
        auth_manager=None,
    )
    set_web_context(ctx)
    app = create_web_app()
    return TestClient(app)


class TestSessionsRoutes:
    """Tests for /api/sessions endpoints."""

    def test_list_sessions(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/sessions returns session list."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.list_sessions = AsyncMock(
            return_value=[
                MagicMock(
                    id="s1",
                    platform="cli",
                    platform_user="u1",
                    started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    last_active_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    state=MagicMock(value="ACTIVE"),
                    temperature=MagicMock(value="COLD"),
                )
            ]
        )

        response = client.get("/api/sessions?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["id"] == "s1"
        ctx.session_store.list_sessions.assert_awaited_once_with(limit=10)

    def test_get_turns(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/sessions/{id}/turns returns turns."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.session_store.list_turns_for_session = AsyncMock(
            return_value=[
                MagicMock(
                    id="t1",
                    session_id="s1",
                    state=MagicMock(value="done"),
                    started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    iterations=1,
                    error=None,
                )
            ]
        )

        response = client.get("/api/sessions/s1/turns")
        assert response.status_code == 200
        data = response.json()
        assert len(data["turns"]) == 1
        assert data["turns"][0]["id"] == "t1"
        ctx.session_store.list_turns_for_session.assert_awaited_once_with("s1")


class TestProposalsRoutes:
    """Tests for /api/proposals endpoints."""

    def test_list_proposals(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/proposals returns filtered proposals."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.proposal_store.list_by_status = AsyncMock(
            return_value=[
                MagicMock(
                    id="p1",
                    type="type_a",
                    summary="sum",
                    evidence=["e1"],
                    action={"a": 1},
                    confidence=0.9,
                    status="pending",
                    created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    expires_at=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
                    reviewed_at=None,
                    review_note=None,
                )
            ]
        )

        response = client.get("/api/proposals?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["proposals"][0]["status"] == "pending"
        ctx.proposal_store.list_by_status.assert_awaited_once_with(status="pending")

    def test_accept_proposal(self, client: TestClient, mock_app: MagicMock) -> None:
        """POST /api/proposals/{id}/accept updates status."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.proposal_store.update_status = AsyncMock(return_value=True)

        response = client.post("/api/proposals/p1/accept")
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        ctx.proposal_store.update_status.assert_awaited_once_with("p1", "accepted")

    def test_reject_proposal(self, client: TestClient, mock_app: MagicMock) -> None:
        """POST /api/proposals/{id}/reject with note updates status."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.proposal_store.update_status = AsyncMock(return_value=True)

        response = client.post("/api/proposals/p1/reject", json={"note": "bad idea"})
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        ctx.proposal_store.update_status.assert_awaited_once_with(
            "p1", "rejected", review_note="bad idea"
        )

    def test_defer_proposal(self, client: TestClient, mock_app: MagicMock) -> None:
        """POST /api/proposals/{id}/defer updates status."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.proposal_store.update_status = AsyncMock(return_value=True)

        response = client.post("/api/proposals/p1/defer")
        assert response.status_code == 200
        assert response.json()["status"] == "deferred"
        ctx.proposal_store.update_status.assert_awaited_once_with("p1", "deferred")

    def test_proposal_not_found(self, client: TestClient, mock_app: MagicMock) -> None:
        """POST returns 404 when proposal does not exist."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.proposal_store.update_status = AsyncMock(return_value=False)

        response = client.post("/api/proposals/missing/accept")
        assert response.status_code == 404


class TestStyleRoutes:
    """Tests for /api/style endpoints."""

    def test_get_profile(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/style/{platform}/{user} returns profile dict."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.style_store.get_profile_dict = AsyncMock(return_value={"formality": 0.8})

        response = client.get("/api/style/cli/u1")
        assert response.status_code == 200
        data = response.json()
        assert data["profile"]["formality"] == 0.8
        ctx.style_store.get_profile_dict.assert_awaited_once_with("cli", "u1")

    def test_delete_metric(self, client: TestClient, mock_app: MagicMock) -> None:
        """DELETE /api/style/{platform}/{user}/{metric} removes metric."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.style_store.delete_metric = AsyncMock(return_value=True)

        response = client.delete("/api/style/cli/u1/formality")
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        ctx.style_store.delete_metric.assert_awaited_once_with("cli", "u1", "formality")

    def test_delete_metric_not_found(self, client: TestClient, mock_app: MagicMock) -> None:
        """DELETE returns 404 when metric does not exist."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.style_store.delete_metric = AsyncMock(return_value=False)

        response = client.delete("/api/style/cli/u1/formality")
        assert response.status_code == 404


class TestSchedulerRoutes:
    """Tests for /api/scheduler endpoints."""

    def test_list_tasks(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/scheduler/tasks returns all tasks."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.scheduler_store.list_tasks_for_session = AsyncMock(
            return_value=[
                MagicMock(
                    id="task1",
                    session_id="s1",
                    prompt="hello",
                    description=None,
                    cron_expression=None,
                    fire_at=None,
                    enabled=True,
                    notify=False,
                    created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    last_run_at=None,
                    next_run_at=None,
                    last_error=None,
                )
            ]
        )

        response = client.get("/api/scheduler/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "task1"
        ctx.scheduler_store.list_tasks_for_session.assert_awaited_once_with(
            session_id=None, include_disabled=True
        )

    def test_run_task(self, client: TestClient, mock_app: MagicMock) -> None:
        """POST /api/scheduler/tasks/{id}/run triggers task."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.scheduler_store.get_task = AsyncMock(
            return_value=MagicMock(id="task1")
        )
        ctx.scheduler_store.run_now = AsyncMock(return_value=True)

        response = client.post("/api/scheduler/tasks/task1/run")
        assert response.status_code == 200
        assert response.json()["triggered"] is True
        ctx.scheduler_store.run_now.assert_awaited_once_with("task1")

    def test_run_task_not_found(self, client: TestClient, mock_app: MagicMock) -> None:
        """POST returns 404 when task does not exist."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.scheduler_store.get_task = AsyncMock(return_value=None)

        response = client.post("/api/scheduler/tasks/missing/run")
        assert response.status_code == 404


class TestTracesRoutes:
    """Tests for /api/traces and /api/failures endpoints."""

    def test_list_traces(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/traces returns traces."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.trace_store.list_recent = AsyncMock(
            return_value=[
                MagicMock(
                    id="tr1",
                    session_id="s1",
                    turn_id="t1",
                    started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    ended_at=None,
                    user_input_summary="hi",
                    tools_called=["terminal"],
                    tool_call_count=1,
                    delegated=False,
                    outcome="success",
                    artifact_handles=[],
                    prompt_tokens=10,
                    completion_tokens=5,
                    reasoning_tokens=None,
                    total_duration_ms=100,
                )
            ]
        )

        response = client.get("/api/traces?session_id=s1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["traces"][0]["outcome"] == "success"
        ctx.trace_store.list_recent.assert_awaited_once_with(session_id="s1", limit=10)

    def test_list_failures(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/failures returns failure bundles."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.failure_store.list_recent = AsyncMock(
            return_value=[
                MagicMock(
                    id="f1",
                    session_id="s1",
                    turn_id="t1",
                    failure_class="timeout",
                    severity="warning",
                    error_message="timed out",
                    tool_chain='["terminal"]',
                    created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                )
            ]
        )

        response = client.get("/api/failures?class=timeout&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["failures"][0]["failure_class"] == "timeout"
        ctx.failure_store.list_recent.assert_awaited_once_with(
            failure_class="timeout", limit=5
        )


class TestDoctorRoute:
    """Tests for /api/doctor endpoint."""

    def test_doctor_check(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/doctor returns health check results."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None

        class FakeResult:
            def __init__(self, name: str, ok: bool, detail: str) -> None:
                self.name = name
                self.ok = ok
                self.detail = detail

        from unittest.mock import patch
        with patch(
            "hestia.web.routes.doctor.run_checks",
            new=AsyncMock(return_value=[FakeResult("python_version", True, "")]),
        ) as mock_run:
            response = client.get("/api/doctor")
            assert response.status_code == 200
            data = response.json()
            assert data["checks"][0]["name"] == "python_version"
            mock_run.assert_awaited_once_with(mock_app)


class TestAuditRoute:
    """Tests for /api/audit endpoint."""

    def test_run_audit(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/audit returns audit report."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None

        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"findings": []}

        from unittest.mock import patch
        with patch(
            "hestia.web.routes.audit.SecurityAuditor",
        ) as MockAuditor:
            instance = MockAuditor.return_value
            instance.run_audit = AsyncMock(return_value=mock_report)
            response = client.get("/api/audit")
            assert response.status_code == 200
            assert response.json()["findings"] == []
            assert response.json()["cached"] is False
            MockAuditor.assert_called_once_with(
                config=mock_app.config,
                tool_registry=mock_app.tool_registry,
                trace_store=ctx.trace_store,
            )


class TestEgressRoute:
    """Tests for /api/egress endpoint."""

    def test_list_egress(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/egress returns egress events."""
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        ctx.trace_store.list_egress = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "session_id": "s1",
                    "url": "https://example.com",
                    "domain": "example.com",
                    "status": 200,
                    "size": 1024,
                    "created_at": "2024-01-01T12:00:00",
                }
            ]
        )

        response = client.get("/api/egress?domain=example.com")
        assert response.status_code == 200
        data = response.json()
        assert data["events"][0]["domain"] == "example.com"
        ctx.trace_store.list_egress.assert_awaited_once_with(
            domain="example.com", since=None
        )


class TestConfigRoute:
    """Tests for /api/config endpoint."""

    def test_get_config(self, client: TestClient, mock_app: MagicMock) -> None:
        """GET /api/config returns masked config."""
        from dataclasses import dataclass

        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None

        @dataclass
        class FakeTokenConfig:
            bot_token: str = "secret"
            allowed_users: list[str] = None  # type: ignore[assignment]

        @dataclass
        class FakeMatrixConfig:
            access_token: str = "secret"
            homeserver: str = ""

        @dataclass
        class FakeConfig:
            telegram: FakeTokenConfig = None  # type: ignore[assignment]
            matrix: FakeMatrixConfig = None  # type: ignore[assignment]

        mock_app.config = FakeConfig(
            telegram=FakeTokenConfig(bot_token="secret"),
            matrix=FakeMatrixConfig(access_token="secret"),
        )

        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data["telegram"]["bot_token"] == "***"
        assert data["matrix"]["access_token"] == "***"

    def test_get_config_schema(self, client: TestClient) -> None:
        """GET /api/config/schema returns enum metadata."""
        response = client.get("/api/config/schema")
        assert response.status_code == 200
        data = response.json()
        assert "schema" in data
        assert data["schema"]["trust.preset"]["type"] == "enum"
        assert "paranoid" in data["schema"]["trust.preset"]["values"]

    def test_put_config_stub(self, client: TestClient, mock_app: MagicMock) -> None:
        """PUT /api/config returns 501 Not Implemented."""
        response = client.put("/api/config")
        assert response.status_code == 501
        assert "not yet implemented" in response.json()["detail"]
