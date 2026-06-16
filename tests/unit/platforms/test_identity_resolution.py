"""Tests for platform identity resolution in group/room sessions (L222 §3)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.config import HestiaConfig, MatrixConfig
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.users import User
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.platforms.runners import PlatformRunner


def _make_session(
    session_id: str = "sess-1",
    state: SessionState = SessionState.ACTIVE,
    platform: str = "fake",
    platform_user: str = "u1",
) -> Session:
    now = datetime.now(UTC)
    return Session(
        id=session_id,
        platform=platform,
        platform_user=platform_user,
        started_at=now,
        last_active_at=now,
        slot_id=None,
        slot_saved_path=None,
        state=state,
        temperature=SessionTemperature.COLD,
    )


def _make_config() -> HestiaConfig:
    config = MagicMock(spec=HestiaConfig)
    config.system_prompt = "You are Hestia."
    config.scheduler = MagicMock()
    config.scheduler.tick_interval_seconds = 60
    config.telegram = MagicMock()
    config.telegram.voice_messages = False
    config.telegram.bot_token = "test-token"
    config.matrix = MagicMock()
    config.matrix.access_token = "test-token"
    config.matrix.user_id = "@bot:matrix.org"
    config.inference = MagicMock()
    config.inference.model_name = "test-model"
    config.inference.stream = False
    config.voice = MagicMock()
    return config


def _make_app() -> MagicMock:
    app = MagicMock()
    app.handoff_service = MagicMock()
    app.handoff_service.get_or_create_session_with_handoff = AsyncMock(
        return_value=_make_session("sess-new")
    )
    app.session_store = MagicMock()
    app.session_store.get_session = AsyncMock(return_value=_make_session())
    app.user_store = MagicMock()
    app.user_store.get_user_by_identity = AsyncMock(return_value=None)
    app.user_store.get_room_by_platform = AsyncMock(return_value=None)
    app.user_store.create_room = AsyncMock()
    app.user_store.get_room_members = AsyncMock(return_value=[])
    app.user_store.add_room_member = AsyncMock()
    app.event_bus = None
    orchestrator = MagicMock()
    orchestrator.process_turn = AsyncMock()
    app.make_orchestrator = MagicMock(return_value=orchestrator)
    return app


def _make_user(user_id: str = "user-1") -> User:
    return User(
        id=user_id,
        display_name="Test User",
        role="user",
        trust_preset=None,
        notes=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestIdentityResolution:
    """Tests that group/room sessions resolve the sender as the trust actor."""

    @pytest.mark.asyncio
    async def test_group_chat_actor_is_sender_not_room(self):
        """In a group/room, resolved_user should be looked up by sender id."""
        app = _make_app()
        config = _make_config()
        runner = PlatformRunner(
            app, config, MagicMock(), app.make_orchestrator.return_value, "fake"
        )
        sender = _make_user("sender-1")
        app.user_store.get_user_by_identity = AsyncMock(return_value=sender)

        await runner.on_message(
            "fake", "room-1", "hello", sender_platform_user="sender-id", session_title=None
        )

        app.user_store.get_user_by_identity.assert_awaited_once_with(
            "fake", "sender-id"
        )
        app.make_orchestrator.return_value.process_turn.assert_awaited_once()
        call_kwargs = app.make_orchestrator.return_value.process_turn.call_args[1]
        assert call_kwargs["resolved_user"] is sender

    @pytest.mark.asyncio
    async def test_private_chat_actor_is_platform_user(self):
        """In a private chat, resolved_user should be looked up by platform_user."""
        app = _make_app()
        config = _make_config()
        runner = PlatformRunner(
            app, config, MagicMock(), app.make_orchestrator.return_value, "fake"
        )
        user = _make_user("user-1")
        app.user_store.get_user_by_identity = AsyncMock(return_value=user)

        await runner.on_message(
            "fake", "user-id", "hello", sender_platform_user=None, session_title=None
        )

        app.user_store.get_user_by_identity.assert_awaited_once_with("fake", "user-id")
        call_kwargs = app.make_orchestrator.return_value.process_turn.call_args[1]
        assert call_kwargs["resolved_user"] is user


class TestMatrixUnknownSenderRejection:
    """Tests that Matrix rejects unknown senders before creating a session."""

    @pytest.mark.asyncio
    async def test_unknown_sender_in_matrix_room_is_rejected(self):
        """A Matrix event from a sender with no identity record is rejected."""
        app = _make_app()
        config = _make_config()
        adapter = MatrixAdapter(
            MatrixConfig(
                access_token="test-token",
                user_id="@bot:matrix.org",
                allowed_rooms=["!room:matrix.org"],
            )
        )
        runner = PlatformRunner(
            app, config, adapter, app.make_orchestrator.return_value, "matrix"
        )
        app.user_store.get_user_by_identity = AsyncMock(return_value=None)

        adapter._on_message = runner.on_message
        adapter.send_error = AsyncMock()

        room = MagicMock()
        room.room_id = "!room:matrix.org"
        event = MagicMock()
        event.sender = "@unknown:matrix.org"
        event.body = "hello"
        event.source = {"content": {}}

        await adapter._handle_room_message(room, event)

        app.user_store.get_user_by_identity.assert_awaited_once_with(
            "matrix", "@unknown:matrix.org"
        )
        app.handoff_service.get_or_create_session_with_handoff.assert_not_awaited()
        app.make_orchestrator.return_value.process_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_known_sender_in_matrix_room_is_accepted(self):
        """A Matrix event from a sender with an identity record is processed."""
        app = _make_app()
        config = _make_config()
        adapter = MatrixAdapter(
            MatrixConfig(
                access_token="test-token",
                user_id="@bot:matrix.org",
                allowed_rooms=["!room:matrix.org"],
            )
        )
        runner = PlatformRunner(
            app, config, adapter, app.make_orchestrator.return_value, "matrix"
        )
        user = _make_user("known-user")
        app.user_store.get_user_by_identity = AsyncMock(return_value=user)

        adapter._on_message = runner.on_message
        adapter.send_message = AsyncMock(return_value="$event")

        room = MagicMock()
        room.room_id = "!room:matrix.org"
        event = MagicMock()
        event.sender = "@known:matrix.org"
        event.body = "hello"
        event.source = {"content": {}}

        await adapter._handle_room_message(room, event)

        app.make_orchestrator.return_value.process_turn.assert_awaited_once()
