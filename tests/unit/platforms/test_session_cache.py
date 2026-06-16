"""Tests for in-memory session cache invalidation across platforms."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.config import HestiaConfig
from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.platforms.base import Platform
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.platforms.runners import PlatformRunner, run_platform
from hestia.platforms.telegram_adapter import TelegramAdapter

_IncomingMessageCallback = Callable[
    [str, str, str, str | None, str | None], Coroutine[Any, Any, None]
]


class FakePlatform(Platform):
    """Fake platform adapter for testing."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.sent_messages: list[tuple[str, str]] = []
        self._on_message: _IncomingMessageCallback | None = None

    @property
    def name(self) -> str:
        return "fake"

    async def start(self, on_message: _IncomingMessageCallback) -> None:
        self.started = True
        self._on_message = on_message

    async def stop(self) -> None:
        self.stopped = True

    async def send_message(self, user: str, text: str) -> str:
        self.sent_messages.append((user, text))
        return "msg-id"

    async def edit_message(self, user: str, msg_id: str, text: str) -> None:
        pass

    async def send_error(self, user: str, text: str) -> None:
        self.sent_messages.append((user, f"ERROR:{text}"))


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


def _make_app() -> MagicMock:
    app = MagicMock()
    app.bootstrap_db = AsyncMock()
    app.set_confirm_callback = MagicMock()
    app.make_orchestrator = MagicMock()
    app.session_store = MagicMock()
    app.session_store.get_session = AsyncMock(return_value=_make_session())
    app.session_store.archive_session = AsyncMock()
    app.session_store.get_active_session = AsyncMock(return_value=_make_session())
    app.session_store.update_session_title = AsyncMock()
    app.handoff_service = MagicMock()
    app.handoff_service.get_or_create_session_with_handoff = AsyncMock(
        return_value=_make_session("sess-new")
    )
    app.user_store = MagicMock()
    app.user_store.get_user_by_identity = AsyncMock(return_value=None)
    app.user_store.get_room_by_platform = AsyncMock(return_value=None)
    app.user_store.create_room = AsyncMock()
    app.user_store.get_room_members = AsyncMock(return_value=[])
    app.user_store.add_room_member = AsyncMock()
    app.inference.close = AsyncMock()
    context_builder = MagicMock()
    context_builder.warm_up = AsyncMock()
    app.context_builder = context_builder
    orchestrator = MagicMock()
    orchestrator.recover_stale_turns = AsyncMock(return_value=0)
    orchestrator.process_turn = AsyncMock()
    app.make_orchestrator.return_value = orchestrator
    return app


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


class TestPlatformRunnerCache:
    """Unit tests for PlatformRunner session cache behavior."""

    @pytest.mark.asyncio
    async def test_invalidate_session_cache_removes_entry(self):
        runner = PlatformRunner(
            MagicMock(), _make_config(), FakePlatform(), MagicMock(), "fake"
        )
        session = _make_session()
        runner.user_sessions["u1"] = session

        runner.invalidate_session_cache("u1")

        assert "u1" not in runner.user_sessions

    @pytest.mark.asyncio
    async def test_invalidate_session_cache_is_idempotent(self):
        runner = PlatformRunner(
            MagicMock(), _make_config(), FakePlatform(), MagicMock(), "fake"
        )

        runner.invalidate_session_cache("u1")

        assert "u1" not in runner.user_sessions

    @pytest.mark.asyncio
    async def test_on_message_caches_session_on_first_message(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        runner = PlatformRunner(app, config, adapter, app.make_orchestrator.return_value, "fake")

        await runner.on_message("fake", "u1", "hello", None, None)

        assert "u1" in runner.user_sessions
        app.handoff_service.get_or_create_session_with_handoff.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_message_reuses_cached_session(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        runner = PlatformRunner(app, config, adapter, app.make_orchestrator.return_value, "fake")
        runner.user_sessions["u1"] = _make_session("sess-existing")

        await runner.on_message("fake", "u1", "hello", None, None)

        assert runner.user_sessions["u1"].id == "sess-existing"
        app.handoff_service.get_or_create_session_with_handoff.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_message_creates_new_session_after_reset(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        runner = PlatformRunner(app, config, adapter, app.make_orchestrator.return_value, "fake")

        # First message creates cache
        await runner.on_message("fake", "u1", "hello", None, None)
        assert "u1" in runner.user_sessions

        # Reset clears cache
        runner.invalidate_session_cache("u1")
        assert "u1" not in runner.user_sessions

        # Next message creates a new session
        app.handoff_service.get_or_create_session_with_handoff.reset_mock()
        await runner.on_message("fake", "u1", "hello again", None, None)

        assert "u1" in runner.user_sessions
        app.handoff_service.get_or_create_session_with_handoff.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_message_invalidates_cache_when_session_archived(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        runner = PlatformRunner(app, config, adapter, app.make_orchestrator.return_value, "fake")

        cached_session = _make_session("sess-1", SessionState.ACTIVE)
        runner.user_sessions["u1"] = cached_session

        # Simulate external archival
        app.session_store.get_session = AsyncMock(
            return_value=_make_session("sess-1", SessionState.ARCHIVED)
        )

        await runner.on_message("fake", "u1", "hello", None, None)

        assert runner.user_sessions["u1"].id == "sess-new"
        app.handoff_service.get_or_create_session_with_handoff.assert_awaited_once()


class TestTelegramReset:
    """Tests for Telegram /reset cache invalidation."""

    @pytest.mark.asyncio
    async def test_reset_handler_archives_session_and_invokes_callback(self):
        from hestia.config import TelegramConfig

        cfg = TelegramConfig(bot_token="test-token", allowed_users=["12345"])
        adapter = TelegramAdapter(cfg)
        mock_store = MagicMock()
        mock_store.get_active_session = AsyncMock(
            return_value=_make_session(
                "sess-1", platform="telegram", platform_user="12345"
            )
        )
        mock_store.archive_session = AsyncMock()
        mock_handoff = MagicMock()
        mock_handoff.generate_handoff_summary = AsyncMock()
        adapter.set_voice_deps(
            orchestrator=MagicMock(),
            session_store=mock_store,
            handoff_service=mock_handoff,
            system_prompt="You are Hestia.",
            voice_config=None,
        )

        reset_callback = AsyncMock()
        adapter.register_reset_callback(reset_callback)

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        update.effective_user.username = "testuser"
        update.effective_chat = MagicMock()
        update.effective_chat.id = 12345
        update.effective_chat.type = "private"
        update.effective_message = MagicMock()
        update.effective_message.reply_text = AsyncMock()

        await adapter._handle_reset(update, None)

        mock_handoff.generate_handoff_summary.assert_awaited_once_with("sess-1")
        reset_callback.assert_awaited_once_with("12345")


class TestMatrixReset:
    """Tests for Matrix /reset cache invalidation."""

    @pytest.mark.asyncio
    async def test_reset_handler_archives_session_and_invokes_callback(self):
        from hestia.config import MatrixConfig

        cfg = MatrixConfig(access_token="test-token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)
        mock_store = MagicMock()
        mock_store.get_active_session = AsyncMock(
            return_value=_make_session(
                "sess-1", platform="matrix", platform_user="!room:matrix.org"
            )
        )
        mock_store.archive_session = AsyncMock()
        adapter.set_session_store(mock_store)

        reset_callback = AsyncMock()
        adapter.register_reset_callback(reset_callback)

        # Mock send_message so we don't need a real Matrix client
        adapter.send_message = AsyncMock(return_value="$event")

        room = MagicMock()
        room.room_id = "!room:matrix.org"
        event = MagicMock()
        event.sender = "@user:matrix.org"

        await adapter._handle_reset(room, event)

        mock_store.archive_session.assert_awaited_once_with("sess-1")
        reset_callback.assert_awaited_once_with("!room:matrix.org")

    @pytest.mark.asyncio
    async def test_handle_room_message_routes_reset_to_handler(self):
        from hestia.config import MatrixConfig

        cfg = MatrixConfig(
            access_token="test-token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)
        mock_store = MagicMock()
        mock_store.get_active_session = AsyncMock(
            return_value=_make_session(
                "sess-1", platform="matrix", platform_user="!room:matrix.org"
            )
        )
        mock_store.archive_session = AsyncMock()
        adapter.set_session_store(mock_store)
        adapter.send_message = AsyncMock(return_value="$event")

        on_message = AsyncMock()
        adapter._on_message = on_message

        room = MagicMock()
        room.room_id = "!room:matrix.org"
        event = MagicMock()
        event.sender = "@user:matrix.org"
        event.body = "/reset"

        await adapter._handle_room_message(room, event)

        mock_store.archive_session.assert_awaited_once_with("sess-1")
        on_message.assert_not_awaited()


class TestRunnerWiring:
    """Tests that run_platform wires reset callbacks correctly."""

    @pytest.mark.asyncio
    async def test_run_platform_wires_telegram_reset_callback(self):
        app = _make_app()
        config = _make_config()
        adapter = MagicMock(spec=TelegramAdapter)
        adapter.set_voice_deps = MagicMock()
        adapter.register_reset_callback = MagicMock()
        adapter.start = AsyncMock()
        adapter.stop = AsyncMock()

        async def raise_keyboard_interrupt(*args: Any, **kwargs: Any) -> None:
            raise KeyboardInterrupt()

        with (
            patch("asyncio.sleep", side_effect=raise_keyboard_interrupt),
            patch("hestia.platforms.runners.PlatformRunner") as mock_runner_cls,
        ):
            runner_instance = MagicMock()
            runner_instance.on_message = AsyncMock()
            runner_instance.invalidate_session_cache = MagicMock()
            mock_runner_cls.return_value = runner_instance

            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=AsyncMock(),
                platform_name="telegram",
            )

            adapter.register_reset_callback.assert_called_once()
            callback = adapter.register_reset_callback.call_args[0][0]
            assert asyncio.iscoroutinefunction(callback)
            await callback("u1")
            runner_instance.invalidate_session_cache.assert_called_once_with("u1")

    @pytest.mark.asyncio
    async def test_run_platform_wires_matrix_reset_callback(self):
        app = _make_app()
        config = _make_config()
        adapter = MagicMock(spec=MatrixAdapter)
        adapter.set_session_store = MagicMock()
        adapter.register_reset_callback = MagicMock()
        adapter.start = AsyncMock()
        adapter.stop = AsyncMock()

        async def raise_keyboard_interrupt(*args: Any, **kwargs: Any) -> None:
            raise KeyboardInterrupt()

        with (
            patch("asyncio.sleep", side_effect=raise_keyboard_interrupt),
            patch("hestia.platforms.runners.PlatformRunner") as mock_runner_cls,
        ):
            runner_instance = MagicMock()
            runner_instance.on_message = AsyncMock()
            runner_instance.invalidate_session_cache = MagicMock()
            mock_runner_cls.return_value = runner_instance

            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=AsyncMock(),
                platform_name="matrix",
            )

            adapter.set_session_store.assert_called_once_with(app.session_store)
            adapter.register_reset_callback.assert_called_once()
            callback = adapter.register_reset_callback.call_args[0][0]
            assert asyncio.iscoroutinefunction(callback)
            await callback("u1")
            runner_instance.invalidate_session_cache.assert_called_once_with("u1")
