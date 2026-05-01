"""Scheduler engine for running scheduled tasks."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from hestia.core.clock import utcnow
from hestia.core.types import Message, ScheduledTask, SessionState
from hestia.events.bus import EventBus
from hestia.orchestrator import Orchestrator
from hestia.persistence.scheduler import SchedulerStore, _calculate_next_run
from hestia.persistence.sessions import SessionStore
from hestia.platforms.notifier import PlatformNotifier
from hestia.runtime_context import scheduler_tick_active

logger = logging.getLogger(__name__)

# Callback the scheduler invokes to deliver a task's response.
# Adapters (CLI, Matrix, etc.) provide their own implementation.
SchedulerResponseCallback = Callable[[ScheduledTask, str], Awaitable[None]]


class Scheduler:
    """Background loop that runs scheduled tasks via the Orchestrator."""

    def __init__(
        self,
        scheduler_store: SchedulerStore,
        session_store: SessionStore,
        orchestrator: Orchestrator,
        response_callback: SchedulerResponseCallback,
        tick_interval_seconds: float = 5.0,
        system_prompt: str | None = None,
        notifier: PlatformNotifier | None = None,
        event_bus: EventBus | None = None,
    ):
        self._scheduler_store = scheduler_store
        self._session_store = session_store
        self._orchestrator = orchestrator
        self._response_callback = response_callback
        self._tick_interval = tick_interval_seconds
        self._system_prompt = system_prompt or "You are a helpful assistant."
        self._notifier = notifier
        self._event_bus = event_bus
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        """Start the background loop. Returns immediately."""
        if self._loop_task is not None:
            raise RuntimeError("Scheduler is already running")
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Signal the loop to stop and wait for it to exit."""
        self._stop_event.set()
        if self._loop_task is not None:
            await self._loop_task
            self._loop_task = None

    async def _run_loop(self) -> None:
        logger.info("Scheduler loop started (tick=%.1fs)", self._tick_interval)
        try:
            while not self._stop_event.is_set():
                try:
                    await self._tick(utcnow())
                except Exception as e:  # noqa: BLE001
                    # Catch-all to prevent scheduler crash on any error
                    logger.exception(
                        "Scheduler tick raised: %s", e
                    )  # Outermost boundary — intentionally broad

                # Sleep until next tick or stop signal, whichever comes first
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._tick_interval,
                    )
        finally:
            logger.info("Scheduler loop exited")

    async def _tick(self, now: datetime) -> None:
        due = await self._scheduler_store.list_due_tasks(now)
        for task in due:
            await self._fire_task(task, now)

    async def run_now(self, task_id: str) -> None:
        """Manually trigger a task immediately. Useful for testing and CLI."""
        task = await self._scheduler_store.get_task(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        await self._fire_task(task, utcnow(), _force=True)

    async def _fire_task(
        self, task: ScheduledTask, now: datetime, *, _force: bool = False
    ) -> None:
        if not _force and not task.enabled:
            logger.warning(
                "Skipping disabled task %s (next_run_at=%s)",
                task.id,
                task.next_run_at,
            )
            return
        logger.info("Firing scheduled task %s", task.id)

        if self._event_bus is not None:
            self._event_bus.publish(
                "schedule_fired",
                {
                    "task_id": task.id,
                    "session_id": task.session_id,
                    "prompt": task.prompt,
                    "description": task.description,
                },
            )

        session = await self._session_store.get_session(task.session_id)
        if session is None or session.state != SessionState.ACTIVE:
            error = f"Session {task.session_id} no longer exists"
            logger.warning(error)
            await self._scheduler_store.update_after_run(
                task.id, error=error, now=now, next_run_at=None
            )
            return

        user_message = Message(role="user", content=task.prompt)

        async def deliver(text: str) -> None:
            await self._response_callback(task, text)
            if task.notify and self._notifier is not None:
                if text.strip() == "SILENT":
                    return
                session_for_notify = await self._session_store.get_session(task.session_id)
                if session_for_notify is not None:
                    await self._notifier.send(
                        session_for_notify.platform,
                        session_for_notify.platform_user,
                        text,
                    )

        turn_error: str | None = None
        tick_token = scheduler_tick_active.set(True)
        try:
            turn = await self._orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=deliver,
                system_prompt=self._system_prompt,
            )
            turn_error = turn.error
        except Exception as e:  # noqa: BLE001
            # Catch-all to record any failure during task execution
            logger.exception(
                "Task %s failed during process_turn", task.id
            )  # Outermost boundary — intentionally broad
            turn_error = str(e)
        finally:
            scheduler_tick_active.reset(tick_token)

        # Compute next run: cron tasks advance, one-shot tasks don't
        if task.cron_expression is not None:
            next_run = _calculate_next_run(task.cron_expression, None, base_time=now)
        else:
            next_run = None  # One-shot tasks don't repeat
        await self._scheduler_store.update_after_run(
            task.id, error=turn_error, now=now, next_run_at=next_run
        )
