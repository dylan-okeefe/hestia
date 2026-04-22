"""Tests for platform runners — routing, lifecycle, and signal handling."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.config import HestiaConfig
from hestia.core.types import Session
from hestia.platforms.base import Platform
from hestia.platforms.runners import (
    make_matrix_confirm_callback,
    make_matrix_scheduler_callback,
    make_telegram_confirm_callback,
    make_telegram_scheduler_callback,
    run_matrix,
    run_platform,
    run_telegram,
)


class FakePlatform(Platform):
    """Fake platform adapter for testing."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.sent_messages: list[tuple[str, str]] = []
        self._on_message: Callable[[str, str, str], Coroutine[Any, Any, None]] | None = None

    @property
    def name(self) -> str:
        return "fake"

    async def start(self, on_message: Callable[[str, str, str], Coroutine[Any, Any, None]]) -> None:
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


def _make_app() -> MagicMock:
    app = MagicMock()
    app.bootstrap_db = AsyncMock()
    app.set_confirm_callback = MagicMock()
    app.make_orchestrator = MagicMock()
    app.session_store = MagicMock()
    app.session_store.get_or_create_session = AsyncMock(
        return_value=Session(
            id="sess-1",
            platform="fake",
            platform_user="u1",
            started_at=MagicMock(),
            last_active_at=MagicMock(),
            slot_id=None,
            slot_saved_path=None,
            state=MagicMock(),
            temperature=MagicMock(),
        )
    )
    app.inference.close = AsyncMock()
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
    config.telegram.bot_token = ""
    config.matrix = MagicMock()
    config.matrix.access_token = ""
    config.matrix.user_id = ""
    config.inference = MagicMock()
    config.inference.model_name = "test-model"
    config.voice = MagicMock()
    return config


class TestConfirmCallbacks:
    """Tests for platform-specific confirm callbacks."""

    @pytest.mark.asyncio
    async def test_telegram_confirm_callback_denies_without_user(self):
        adapter = MagicMock()
        adapter.request_confirmation = AsyncMock(return_value=True)
        var: ContextVar[str] = ContextVar("user", default="")
        callback = make_telegram_confirm_callback(adapter, var)
        result = await callback("terminal", {"command": "ls"})
        assert result is False
        adapter.request_confirmation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_telegram_confirm_callback_approves_with_user(self):
        adapter = MagicMock()
        adapter.request_confirmation = AsyncMock(return_value=True)
        var: ContextVar[str] = ContextVar("user", default="")
        token = var.set("@alice")
        try:
            callback = make_telegram_confirm_callback(adapter, var)
            result = await callback("terminal", {"command": "ls"})
            assert result is True
            adapter.request_confirmation.assert_awaited_once_with(
                "@alice", "terminal", {"command": "ls"}
            )
        finally:
            var.reset(token)

    @pytest.mark.asyncio
    async def test_matrix_confirm_callback_denies_without_room(self):
        adapter = MagicMock()
        adapter.request_confirmation = AsyncMock(return_value=True)
        var: ContextVar[str] = ContextVar("room", default="")
        callback = make_matrix_confirm_callback(adapter, var)
        result = await callback("terminal", {"command": "ls"})
        assert result is False
        adapter.request_confirmation.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_matrix_confirm_callback_approves_with_room(self):
        adapter = MagicMock()
        adapter.request_confirmation = AsyncMock(return_value=True)
        var: ContextVar[str] = ContextVar("room", default="")
        token = var.set("!room:example.com")
        try:
            callback = make_matrix_confirm_callback(adapter, var)
            result = await callback("terminal", {"command": "ls"})
            assert result is True
            adapter.request_confirmation.assert_awaited_once_with(
                "!room:example.com", "terminal", {"command": "ls"}
            )
        finally:
            var.reset(token)


class TestSchedulerCallbacks:
    """Tests for scheduler response callbacks."""

    @pytest.mark.asyncio
    async def test_telegram_scheduler_routes_to_correct_platform(self):
        adapter = MagicMock()
        adapter.send_message = AsyncMock()
        session_store = MagicMock()
        session_store.get_session = AsyncMock(
            return_value=MagicMock(platform="telegram", platform_user="@alice")
        )
        callback = make_telegram_scheduler_callback(adapter, session_store)
        task = MagicMock()
        task.id = "task-1"
        task.session_id = "sess-1"
        await callback(task, "Hello")
        adapter.send_message.assert_awaited_once_with("@alice", "Hello")

    @pytest.mark.asyncio
    async def test_telegram_scheduler_skips_wrong_platform(self):
        adapter = MagicMock()
        adapter.send_message = AsyncMock()
        session_store = MagicMock()
        session_store.get_session = AsyncMock(
            return_value=MagicMock(platform="matrix", platform_user="@alice")
        )
        callback = make_telegram_scheduler_callback(adapter, session_store)
        task = MagicMock()
        task.id = "task-1"
        task.session_id = "sess-1"
        await callback(task, "Hello")
        adapter.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_matrix_scheduler_routes_to_correct_platform(self):
        adapter = MagicMock()
        adapter.send_message = AsyncMock()
        session_store = MagicMock()
        session_store.get_session = AsyncMock(
            return_value=MagicMock(platform="matrix", platform_user="@alice")
        )
        callback = make_matrix_scheduler_callback(adapter, session_store)
        task = MagicMock()
        task.id = "task-1"
        task.session_id = "sess-1"
        await callback(task, "Hello")
        adapter.send_message.assert_awaited_once_with("@alice", "Hello")

    @pytest.mark.asyncio
    async def test_matrix_scheduler_skips_wrong_platform(self):
        adapter = MagicMock()
        adapter.send_message = AsyncMock()
        session_store = MagicMock()
        session_store.get_session = AsyncMock(
            return_value=MagicMock(platform="telegram", platform_user="@alice")
        )
        callback = make_matrix_scheduler_callback(adapter, session_store)
        task = MagicMock()
        task.id = "task-1"
        task.session_id = "sess-1"
        await callback(task, "Hello")
        adapter.send_message.assert_not_awaited()


class TestRunPlatformLifecycle:
    """Tests for run_platform startup/shutdown lifecycle."""

    @pytest.mark.asyncio
    async def test_starts_adapter_and_orchestrator(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        confirm_callback = AsyncMock(return_value=True)

        async def raise_keyboard_interrupt(*args: Any, **kwargs: Any) -> None:
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=raise_keyboard_interrupt):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=confirm_callback,
                platform_name="fake",
            )

        assert adapter.started is True
        assert adapter.stopped is True
        app.bootstrap_db.assert_awaited_once()
        app.set_confirm_callback.assert_called_once_with(confirm_callback)
        app.make_orchestrator.assert_called_once()
        app.inference.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_cancelled_error(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        confirm_callback = AsyncMock(return_value=True)

        async def raise_cancelled(*args: Any, **kwargs: Any) -> None:
            raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=raise_cancelled):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=confirm_callback,
                platform_name="fake",
            )

        assert adapter.stopped is True
        app.inference.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_incoming_message(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        confirm_callback = AsyncMock(return_value=True)
        user_var: ContextVar[str] = ContextVar("user", default="")

        async def single_message_then_stop(*args: Any, **kwargs: Any) -> None:
            if adapter._on_message is not None:
                await adapter._on_message("fake", "u1", "hello")
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=single_message_then_stop):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=confirm_callback,
                platform_name="fake",
                user_context_var=user_var,
            )

        orchestrator = app.make_orchestrator.return_value
        orchestrator.process_turn.assert_awaited_once()
        call_kwargs = orchestrator.process_turn.call_args.kwargs
        assert call_kwargs["platform_user"] == "u1"
        assert call_kwargs["platform"] is adapter

    @pytest.mark.asyncio
    async def test_sends_error_on_turn_exception(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        confirm_callback = AsyncMock(return_value=True)
        orchestrator = app.make_orchestrator.return_value
        orchestrator.process_turn = AsyncMock(side_effect=RuntimeError("boom"))

        async def single_message_then_stop(*args: Any, **kwargs: Any) -> None:
            if adapter._on_message is not None:
                await adapter._on_message("fake", "u1", "hello")
            raise KeyboardInterrupt()

        with patch("asyncio.sleep", side_effect=single_message_then_stop):
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=confirm_callback,
                platform_name="fake",
            )

        assert any("ERROR:Turn failed" in msg for _user, msg in adapter.sent_messages)

    @pytest.mark.asyncio
    async def test_starts_scheduler_when_callback_provided(self):
        app = _make_app()
        config = _make_config()
        adapter = FakePlatform()
        confirm_callback = AsyncMock(return_value=True)
        scheduler_callback = AsyncMock()

        async def raise_keyboard_interrupt(*args: Any, **kwargs: Any) -> None:
            raise KeyboardInterrupt()

        with (
            patch("asyncio.sleep", side_effect=raise_keyboard_interrupt),
            patch("hestia.platforms.runners.Scheduler") as mock_scheduler_cls,
        ):
            scheduler_instance = MagicMock()
            scheduler_instance.start = AsyncMock()
            scheduler_instance.stop = AsyncMock()
            mock_scheduler_cls.return_value = scheduler_instance
            await run_platform(
                app,
                config,
                adapter=adapter,
                confirm_callback=confirm_callback,
                platform_name="fake",
                scheduler_response_callback=scheduler_callback,
            )

        scheduler_instance.start.assert_awaited_once()
        scheduler_instance.stop.assert_awaited_once()


class TestPlatformRouting:
    """Tests for platform-specific runner routing."""

    @pytest.mark.asyncio
    async def test_run_telegram_requires_model_name(self):
        app = _make_app()
        config = _make_config()
        config.inference.model_name = ""
        with pytest.raises(ValueError, match="model_name is required"):
            await run_telegram(app, config)

    @pytest.mark.asyncio
    async def test_run_telegram_requires_bot_token(self):
        app = _make_app()
        config = _make_config()
        config.telegram.bot_token = ""
        with patch("hestia.platforms.runners.TelegramAdapter") as mock_adapter_cls:
            with pytest.raises(SystemExit) as exc_info:
                await run_telegram(app, config)
            assert exc_info.value.code == 1
            mock_adapter_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_matrix_requires_model_name(self):
        app = _make_app()
        config = _make_config()
        config.inference.model_name = ""
        with pytest.raises(ValueError, match="model_name is required"):
            await run_matrix(app, config)

    @pytest.mark.asyncio
    async def test_run_matrix_requires_access_token(self):
        app = _make_app()
        config = _make_config()
        config.matrix.access_token = ""
        with patch("hestia.platforms.runners.MatrixAdapter") as mock_adapter_cls:
            with pytest.raises(SystemExit) as exc_info:
                await run_matrix(app, config)
            assert exc_info.value.code == 1
            mock_adapter_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_matrix_requires_user_id(self):
        app = _make_app()
        config = _make_config()
        config.matrix.user_id = ""
        with patch("hestia.platforms.runners.MatrixAdapter") as mock_adapter_cls:
            with pytest.raises(SystemExit) as exc_info:
                await run_matrix(app, config)
            assert exc_info.value.code == 1
            mock_adapter_cls.assert_not_called()
