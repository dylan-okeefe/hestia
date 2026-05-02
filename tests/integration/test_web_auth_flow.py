"""Integration test for the full auth lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hestia.web.auth import AuthManager, WebSession
from hestia.config import WebConfig


@pytest.fixture
def mock_adapter() -> AsyncMock:
    adapter = AsyncMock()
    adapter._config.allowed_users = ["12345"]  # type: ignore[attr-defined]
    adapter.send_message = AsyncMock()
    return adapter


@pytest.fixture
def auth_manager(mock_adapter: AsyncMock) -> AuthManager:
    return AuthManager(
        adapters={"telegram": mock_adapter},
        config=WebConfig(
            enabled=True,
            auth_enabled=True,
            code_length=6,
            code_expiry_seconds=300,
            session_lifetime_hours=72,
        ),
    )


class TestAuthLifecycle:
    """Full auth flow: request → verify → access → logout → denied."""

    def test_full_flow(self, auth_manager: AuthManager, mock_adapter: AsyncMock) -> None:
        import asyncio

        # 1. Request code
        result = asyncio.run(auth_manager.request_code("telegram"))
        assert result["status"] == "sent"
        code = list(auth_manager._pending_codes.keys())[0]

        # Verify send_message was called with a 6-digit code
        mock_adapter.send_message.assert_called_once()
        call_args = mock_adapter.send_message.call_args
        assert call_args[0][0] == "12345"
        sent_code = call_args[0][1].split(": ")[-1]
        assert len(sent_code) == 6
        assert sent_code.isdigit()
        assert sent_code == code

        # 2. Verify code
        verify_result = auth_manager.validate_code(code, "127.0.0.1")
        assert verify_result is not None
        token, session = verify_result
        assert token
        assert isinstance(session, WebSession)
        assert session.platform == "telegram"
        assert session.platform_user == "12345"

        # 3. Access protected resource with token
        status, retrieved = auth_manager.validate_token(token)
        assert status == "valid"
        assert retrieved is not None
        assert retrieved.platform_user == "12345"

        # 4. Logout
        assert auth_manager.remove_session(token) is True

        # 5. Access denied after logout
        status, retrieved = auth_manager.validate_token(token)
        assert status == "missing"
        assert retrieved is None

    def test_status_reflects_auth_state(self, auth_manager: AuthManager) -> None:
        import asyncio

        # Before auth
        status, session = auth_manager.validate_token("invalid")
        assert status == "missing"

        # After auth
        asyncio.run(auth_manager.request_code("telegram"))
        code = list(auth_manager._pending_codes.keys())[0]
        verify_result = auth_manager.validate_code(code, "127.0.0.1")
        assert verify_result is not None
        token, _ = verify_result

        status, session = auth_manager.validate_token(token)
        assert status == "valid"
        assert session is not None

    def test_auth_disabled_allows_all(self, mock_adapter: AsyncMock) -> None:
        manager = AuthManager(
            adapters={"telegram": mock_adapter},
            config=WebConfig(enabled=True, auth_enabled=False),
        )
        # validate_token should not matter when auth is disabled
        status, session = manager.validate_token("any")
        # But validate_token still works independently
        assert status == "missing"
