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
from hestia.core.types import Message, ScheduledTask, Session, SessionState
from hestia.orchestrator.engine import ConfirmCallback
from hestia.orchestrator.finalization import sanitize_user_error
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.session_store import SessionStore
from hestia.platforms.base import Platform
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.platforms.telegram_adapter import TelegramAdapter
from hestia.policy.channel import Channel
from hestia.scheduler import Scheduler

logger = logging.getLogger(__name__)

# Platform identity of the user whose action triggered the current turn. Used
# to bind interactive confirmations to the requester (especially important in
# group/room chats where the destination is a chat/room id, not the sender).
current_requester: ContextVar[str | None] = ContextVar("current_requester", default=None)


def make_telegram_confirm_callback(
    adapter: TelegramAdapter, current_user_var: ContextVar[str]
) -> ConfirmCallback:
    """Create a confirmation callback wired to Telegram inline keyboard."""

    async def callback(
        tool_name: str, arguments: dict[str, object], request_token: str | None = None
    ) -> bool:
        platform_user = current_user_var.get()
        if not platform_user:
            logger.warning(
                "Telegram confirmation requested without bound platform_user; denying tool '%s'",
                tool_name,
            )
            return False
        requester = current_requester.get() or platform_user
        return await adapter.request_confirmation(
            platform_user,
            tool_name,
            arguments,
            requester_platform_user=requester,
            request_token=request_token,
        )

    return callback


def make_matrix_confirm_callback(
    adapter: MatrixAdapter, current_room_var: ContextVar[str]
) -> ConfirmCallback:
    """Create a confirmation callback wired to Matrix reply pattern."""

    async def callback(
        tool_name: str, arguments: dict[str, object], request_token: str | None = None
    ) -> bool:
        room_id = current_room_var.get()
        if not room_id:
            logger.warning(
                "Matrix confirmation requested without bound room_id; denying tool '%s'",
                tool_name,
            )
            return False
        requester = current_requester.get() or room_id
        return await adapter.request_confirmation(
            room_id,
            tool_name,
            arguments,
            requester_platform_user=requester,
            request_token=request_token,
        )

    return callback


def make_serve_scheduler_callback(
    adapters: dict[str, Any], session_store: SessionStore
) -> Callable[[ScheduledTask, str], Coroutine[Any, Any, None]]:
    """Create a scheduler response callback that routes to any started adapter.

    Used by ``hestia serve`` so a single scheduler can deliver scheduled
    messages to Telegram, Matrix, or other platforms.
    """

    async def callback(task: ScheduledTask, text: str) -> None:
        session = await session_store.get_session(task.session_id)
        if session is None:
            logger.warning("Scheduler task %s: session not found", task.id)
            return
        adapter = adapters.get(session.platform)
        if adapter is None:
            logger.warning(
                "Scheduler task %s: no adapter for platform %s", task.id, session.platform
            )
            return
        await adapter.send_message(session.platform_user, text)

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


class PlatformRunner:
    """Per-platform message loop and in-memory session cache.

    ``PlatformRunner`` owns the ``user_sessions`` cache and exposes a single
    helper, ``invalidate_session_cache``, so platform adapters can drop a cached
    entry when a session is reset or archived.
    """

    def __init__(
        self,
        app: Any,
        config: HestiaConfig,
        adapter: Platform,
        orchestrator: Any,
        platform_name: str,
        user_label: str = "user",
        user_context_var: ContextVar[str] | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.adapter = adapter
        self.orchestrator = orchestrator
        self.platform_name = platform_name
        self.user_label = user_label
        self.user_context_var = user_context_var
        # Session cache: platform_user -> Session
        self.user_sessions: dict[str, Session] = {}

    def invalidate_session_cache(self, platform_user: str) -> None:
        """Drop the cached session for ``platform_user`` and prune its lock.

        Called by platform adapters when a session is reset or archived.
        Also releases the per-session lock so ``SessionLockManager._locks``
        does not grow unbounded.
        """
        session = self.user_sessions.pop(platform_user, None)
        if session is not None:
            lock_manager = getattr(self.orchestrator, "_lock_manager", None)
            if lock_manager is not None:
                lock_manager.release_unused(session.id)

    async def on_message(
        self,
        platform_name_arg: str,
        platform_user: str,
        text: str,
        sender_platform_user: str | None = None,
        session_title: str | None = None,
    ) -> None:
        """Handle incoming platform message."""
        token = None
        requester_token = None
        if self.user_context_var is not None:
            token = self.user_context_var.set(platform_user)
            requester_token = current_requester.set(
                sender_platform_user or platform_user
            )
        try:
            # Resolve the trust actor before creating a session so unknown
            # senders in group/room contexts are rejected before any session
            # or side-effect is created.
            resolved_user = None
            if sender_platform_user is not None:
                # Group chat: resolve individual sender
                resolved_user = await self.app.user_store.get_user_by_identity(
                    self.platform_name, sender_platform_user
                )
            else:
                # Private chat: resolve platform_user directly
                resolved_user = await self.app.user_store.get_user_by_identity(
                    self.platform_name, platform_user
                )

            # In group/room contexts the actor must be a known identity.
            if sender_platform_user is not None and resolved_user is None:
                logger.warning(
                    "Rejecting message from unknown sender %s in %s %s",
                    sender_platform_user,
                    self.platform_name,
                    platform_user,
                )
                return

            if platform_user not in self.user_sessions:
                session = await self.app.handoff_service.get_or_create_session_with_handoff(
                    self.platform_name, platform_user, title=session_title
                )
                self.user_sessions[platform_user] = session
            else:
                session = self.user_sessions[platform_user]
                # Re-fetch the session to detect external archival (e.g., /reset
                # from another adapter, admin action, scheduler cleanup).
                fresh_session = await self.app.session_store.get_session(session.id)
                if fresh_session is None or fresh_session.state == SessionState.ARCHIVED:
                    self.invalidate_session_cache(platform_user)
                    session = await self.app.handoff_service.get_or_create_session_with_handoff(
                        self.platform_name, platform_user, title=session_title
                    )
                    self.user_sessions[platform_user] = session
                elif session_title is not None:
                    await self.app.session_store.update_session_title(
                        session.id, session_title
                    )

            user_message = Message(role="user", content=text)

            # Auto-register room and membership for group chats
            if sender_platform_user is not None and resolved_user is not None:
                room = await self.app.user_store.get_room_by_platform(
                    self.platform_name, platform_user
                )
                if room is None:
                    room = await self.app.user_store.create_room(
                        self.platform_name, platform_user
                    )
                # Add member if not already present
                members = await self.app.user_store.get_room_members(room.id)
                member_ids = {m.id for m in members}
                if resolved_user.id not in member_ids:
                    await self.app.user_store.add_room_member(room.id, resolved_user.id)

            stream_callback = None
            if getattr(self.config.inference, "stream", False) and hasattr(
                self.adapter, "_make_stream_callback"
            ):
                stream_callback = self.adapter._make_stream_callback(platform_user)

            async def respond(response_text: str) -> None:
                stream_states = getattr(self.adapter, "_stream_states", {})
                state = stream_states.get(platform_user, {})
                msg_id = state.get("message_id")
                if stream_callback is not None and msg_id is not None:
                    try:
                        await self.adapter.edit_message(
                            platform_user,
                            msg_id,
                            response_text,
                            fallback_to_new_message=True,
                        )
                        return
                    except Exception as e:  # noqa: BLE001 — delivery boundary
                        logger.warning(
                            "Final stream edit failed for %s, sending new message: %s",
                            platform_user,
                            e,
                        )
                    finally:
                        # Clear the streamed message id so the next turn starts
                        # fresh even if this edit or send raises.
                        state.pop("message_id", None)
                await self.adapter.send_message(platform_user, response_text)

            channel = (
                Channel.TELEGRAM if self.platform_name == "telegram" else Channel.MATRIX
            )
            await self.orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=respond,
                system_prompt=self.config.system_prompt,
                platform=self.adapter,
                platform_user=platform_user,
                stream_callback=stream_callback,
                resolved_user=resolved_user,
                channel=channel,
            )

            # Check for command prefix (e.g., "/workflow ")
            if text.startswith("/"):
                parts = text[1:].split(None, 1)
                command = parts[0] if parts else ""
                args = parts[1] if len(parts) > 1 else ""
                if self.app.event_bus is not None:
                    await self.app.event_bus.publish("chat_command", {
                        "command": command,
                        "args": args,
                        "platform": self.platform_name,
                        "platform_user": platform_user,
                        "text": text,
                    })

            # Always publish message_matched for pattern matching
            if self.app.event_bus is not None:
                await self.app.event_bus.publish("message_matched", {
                    "text": text,
                    "platform": self.platform_name,
                    "platform_user": platform_user,
                })
        except Exception as e:  # noqa: BLE001 — outermost boundary — intentionally broad
            logger.exception("Turn failed for %s %s", self.user_label, platform_user)
            await self.adapter.send_error(platform_user, sanitize_user_error(e))
        finally:
            if token is not None:
                self.user_context_var.reset(token)  # type: ignore[union-attr]
            if requester_token is not None:
                current_requester.reset(requester_token)


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

    runner = PlatformRunner(
        app,
        config,
        adapter,
        orchestrator,
        platform_name,
        user_label=user_label,
        user_context_var=user_context_var,
    )

    # Inject runtime deps into Telegram adapter (session store, orchestrator,
    # system prompt). Voice config is only required when voice messages are enabled.
    async def _reset_callback(platform_user: str) -> None:
        runner.invalidate_session_cache(platform_user)

    if isinstance(adapter, TelegramAdapter):
        adapter.set_voice_deps(
            orchestrator=orchestrator,
            session_store=app.session_store,
            handoff_service=app.handoff_service,
            system_prompt=config.system_prompt,
            voice_config=config.voice if config.telegram.voice_messages else None,
        )
        adapter.register_reset_callback(_reset_callback)
        adapter.set_compactor(app.compactor)
    elif isinstance(adapter, MatrixAdapter):
        adapter.set_session_store(app.session_store)
        adapter.register_reset_callback(_reset_callback)
        adapter.set_compactor(app.compactor)

    # Recover stale turns from previous crash
    recovered = await orchestrator.recover_stale_turns()
    if recovered:
        click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

    await adapter.start(runner.on_message)
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
            event_bus=app.event_bus,
            blocked_actions_digest=app.blocked_actions_digest,
            memory_maintenance=app.memory_maintenance,
            memory_maintenance_digest=app.memory_maintenance_digest,
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


async def run_telegram(
    app: Any,
    config: HestiaConfig,
    adapter: TelegramAdapter | None = None,
    start_scheduler: bool = True,
) -> None:
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

    if adapter is None:
        adapter = TelegramAdapter(config.telegram)
    current_telegram_user: ContextVar[str] = ContextVar("current_telegram_user", default="")
    confirm_callback = make_telegram_confirm_callback(adapter, current_telegram_user)
    scheduler_response_callback: (
        Callable[[ScheduledTask, str], Coroutine[Any, Any, None]] | None
    ) = None
    if start_scheduler:
        scheduler_response_callback = make_telegram_scheduler_callback(adapter, app.session_store)

    await run_platform(
        app,
        config,
        adapter=adapter,
        confirm_callback=confirm_callback,
        platform_name="telegram",
        user_label="user",
        scheduler_response_callback=scheduler_response_callback,
        user_context_var=current_telegram_user,
    )


async def run_matrix(
    app: Any,
    config: HestiaConfig,
    adapter: MatrixAdapter | None = None,
    start_scheduler: bool = True,
) -> None:
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

    if adapter is None:
        adapter = MatrixAdapter(config.matrix)
    current_matrix_room: ContextVar[str] = ContextVar("current_matrix_room", default="")
    confirm_callback = make_matrix_confirm_callback(adapter, current_matrix_room)
    scheduler_response_callback: (
        Callable[[ScheduledTask, str], Coroutine[Any, Any, None]] | None
    ) = None
    if start_scheduler:
        scheduler_response_callback = make_matrix_scheduler_callback(adapter, app.session_store)

    await run_platform(
        app,
        config,
        adapter=adapter,
        confirm_callback=confirm_callback,
        platform_name="matrix",
        user_label="room",
        scheduler_response_callback=scheduler_response_callback,
        user_context_var=current_matrix_room,
    )
