"""Platform-specific runtime loops for Telegram and Matrix."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import Any

import click

from hestia.config import HestiaConfig
from hestia.core.types import Message, ScheduledTask, Session
from hestia.orchestrator.engine import ConfirmCallback
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.platforms.base import Platform
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.platforms.telegram_adapter import TelegramAdapter
from hestia.scheduler import Scheduler

logger = logging.getLogger(__name__)


def make_telegram_confirm_callback(
    adapter: TelegramAdapter, current_user_var: ContextVar[str]
) -> ConfirmCallback:
    """Create a confirmation callback wired to Telegram inline keyboard."""

    async def callback(tool_name: str, arguments: dict[str, object]) -> bool:
        platform_user = current_user_var.get()
        if not platform_user:
            logger.warning(
                "Telegram confirmation requested without bound platform_user; denying tool '%s'",
                tool_name,
            )
            return False
        return await adapter.request_confirmation(platform_user, tool_name, arguments)

    return callback


def make_matrix_confirm_callback(
    adapter: MatrixAdapter, current_room_var: ContextVar[str]
) -> ConfirmCallback:
    """Create a confirmation callback wired to Matrix reply pattern."""

    async def callback(tool_name: str, arguments: dict[str, object]) -> bool:
        room_id = current_room_var.get()
        if not room_id:
            logger.warning(
                "Matrix confirmation requested without bound room_id; denying tool '%s'",
                tool_name,
            )
            return False
        return await adapter.request_confirmation(room_id, tool_name, arguments)

    return callback


def make_telegram_scheduler_callback(
    adapter: TelegramAdapter, session_store: SessionStore
) -> Callable[[ScheduledTask, str], Coroutine[Any, Any, None]]:
    """Create a scheduler response callback that routes to Telegram."""

    async def callback(task: ScheduledTask, text: str) -> None:
        session = await session_store.get_session(task.session_id)
        if session is None or session.platform != "telegram":
            logger.warning("Scheduler task %s: session not found or not telegram", task.id)
            return
        await adapter.send_message(session.platform_user, text)

    return callback


def make_matrix_scheduler_callback(
    adapter: MatrixAdapter, session_store: SessionStore
) -> Callable[[ScheduledTask, str], Coroutine[Any, Any, None]]:
    """Create a scheduler response callback that routes to Matrix."""

    async def callback(task: ScheduledTask, text: str) -> None:
        session = await session_store.get_session(task.session_id)
        if session is None or session.platform != "matrix":
            logger.warning("Scheduler task %s: session not found or not matrix", task.id)
            return
        await adapter.send_message(session.platform_user, text)

    return callback


async def run_platform(
    app: Any,
    config: HestiaConfig,
    *,
    adapter: Platform,
    confirm_callback: ConfirmCallback,
    platform_name: str,
    user_label: str = "user",
    scheduler_response_callback: (
        Callable[[ScheduledTask, str], Coroutine[Any, Any, None]] | None
    ) = None,
    user_context_var: ContextVar[str] | None = None,
) -> None:
    """Shared platform polling loop. Used by run_telegram and run_matrix."""


    # Ensure database is ready
    await app.bootstrap_db()

    # Build orchestrator with platform-specific confirm callback
    app.set_confirm_callback(confirm_callback)
    orchestrator = app.make_orchestrator()

    # Eagerly warm up context builder to avoid first-turn latency
    await app.context_builder.warm_up()

    # Inject voice deps into Telegram adapter when voice messages are enabled
    if isinstance(adapter, TelegramAdapter) and config.telegram.voice_messages:
        adapter.set_voice_deps(
            orchestrator=orchestrator,
            session_store=app.session_store,
            system_prompt=config.system_prompt,
            voice_config=config.voice,
        )

    # Recover stale turns from previous crash
    recovered = await orchestrator.recover_stale_turns()
    if recovered:
        click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

    # Session cache: platform_user -> Session
    user_sessions: dict[str, Session] = {}

    async def on_message(platform_name_arg: str, platform_user: str, text: str) -> None:
        """Handle incoming platform message."""
        token = user_context_var.set(platform_user) if user_context_var is not None else None
        try:
            if platform_user not in user_sessions:
                session = await app.session_store.get_or_create_session(
                    platform_name, platform_user
                )
                user_sessions[platform_user] = session
            else:
                session = user_sessions[platform_user]

            user_message = Message(role="user", content=text)

            stream_callback = None
            if getattr(config.inference, "stream", False) and hasattr(
                adapter, "_make_stream_callback"
            ):
                stream_callback = adapter._make_stream_callback(platform_user)

            async def respond(response_text: str) -> None:
                if stream_callback is not None:
                    state = getattr(adapter, "_stream_states", {}).get(
                        platform_user, {}
                    )
                    msg_id = state.get("message_id")
                    if msg_id is not None:
                        await adapter.edit_message(platform_user, msg_id, response_text)
                        return
                await adapter.send_message(platform_user, response_text)

            await orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=respond,
                system_prompt=config.system_prompt,
                platform=adapter,
                platform_user=platform_user,
                stream_callback=stream_callback,
            )
        except Exception as e:  # noqa: BLE001 — outermost boundary — intentionally broad
            logger.exception("Turn failed for %s %s", user_label, platform_user)
            await adapter.send_error(platform_user, f"Turn failed: {e}")
        finally:
            if token is not None:
                user_context_var.reset(token)  # type: ignore[union-attr]

    await adapter.start(on_message)
    click.echo(f"{platform_name.capitalize()} bot started. Press Ctrl-C to stop.")

    # Also start the scheduler if a response callback was provided
    scheduler: Scheduler | None = None
    if scheduler_response_callback is not None:
        scheduler_store = SchedulerStore(app.db)
        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=app.session_store,
            orchestrator=orchestrator,
            response_callback=scheduler_response_callback,
            tick_interval_seconds=config.scheduler.tick_interval_seconds,
            system_prompt=config.system_prompt,
        )
        await scheduler.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if scheduler is not None:
            await scheduler.stop()
        await adapter.stop()
        await app.inference.close()


async def run_telegram(app: Any, config: HestiaConfig) -> None:
    """Run Hestia as a Telegram bot (blocks until Ctrl-C)."""
    if not config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )

    if not config.telegram.bot_token:
        click.echo("Error: telegram.bot_token is required in config.", err=True)
        click.echo("Set it in your config file or via environment.", err=True)
        sys.exit(1)

    adapter = TelegramAdapter(config.telegram)
    current_telegram_user: ContextVar[str] = ContextVar("current_telegram_user", default="")
    confirm_callback = make_telegram_confirm_callback(adapter, current_telegram_user)
    scheduler_callback = make_telegram_scheduler_callback(adapter, app.session_store)

    await run_platform(
        app,
        config,
        adapter=adapter,
        confirm_callback=confirm_callback,
        platform_name="telegram",
        user_label="user",
        scheduler_response_callback=scheduler_callback,
        user_context_var=current_telegram_user,
    )


async def run_matrix(app: Any, config: HestiaConfig) -> None:
    """Run Hestia as a Matrix bot (blocks until Ctrl-C)."""
    if not config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )

    if not config.matrix.access_token:
        click.echo("Error: matrix.access_token is required in config.", err=True)
        click.echo("Set it in your config file or via environment.", err=True)
        sys.exit(1)

    if not config.matrix.user_id:
        click.echo("Error: matrix.user_id is required in config.", err=True)
        sys.exit(1)

    adapter = MatrixAdapter(config.matrix)
    current_matrix_room: ContextVar[str] = ContextVar("current_matrix_room", default="")
    confirm_callback = make_matrix_confirm_callback(adapter, current_matrix_room)
    scheduler_callback = make_matrix_scheduler_callback(adapter, app.session_store)

    await run_platform(
        app,
        config,
        adapter=adapter,
        confirm_callback=confirm_callback,
        platform_name="matrix",
        user_label="room",
        scheduler_response_callback=scheduler_callback,
        user_context_var=current_matrix_room,
    )
