"""Scheduler engine for running scheduled tasks."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from hestia.blocked_actions.digest import BlockedActionsDigest
from hestia.core.clock import utcnow
from hestia.core.types import Message, ScheduledTask, SessionState
from hestia.events.bus import EventBus
from hestia.memory.maintenance import MemoryMaintenance
from hestia.memory.maintenance.digest import MemoryMaintenanceDigest
from hestia.memory.maintenance.scheduler import _parse_task_prompt
from hestia.orchestrator import Orchestrator
from hestia.persistence.scheduler import (
    _MIN_RETRY_BACKOFF_SECONDS,
    SchedulerStore,
    _calculate_next_run,
)
from hestia.persistence.session_store import SessionStore
from hestia.platforms.notifier import PlatformNotifier
from hestia.policy.channel import Channel
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
        blocked_actions_digest: BlockedActionsDigest | None = None,
        memory_maintenance: MemoryMaintenance | None = None,
        memory_maintenance_digest: MemoryMaintenanceDigest | None = None,
    ):
        self._scheduler_store = scheduler_store
        self._session_store = session_store
        self._orchestrator = orchestrator
        self._response_callback = response_callback
        self._tick_interval = tick_interval_seconds
        self._system_prompt = system_prompt or "You are a helpful assistant."
        self._notifier = notifier
        self._event_bus = event_bus
        self._blocked_actions_digest = blocked_actions_digest
        self._memory_maintenance = memory_maintenance
        self._memory_maintenance_digest = memory_maintenance_digest
        self._tick_lock = asyncio.Lock()
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

    def _backoff_next_run(self, now: datetime) -> datetime:
        """Return a future time for the next retry after a failed run."""
        return now + timedelta(seconds=_MIN_RETRY_BACKOFF_SECONDS)

    def _in_flight_next_run(
        self, task: ScheduledTask, now: datetime
    ) -> datetime:
        """Return the next_run_at value to write before dispatching a task.

        For cron tasks this is the computed next occurrence; for one-shot tasks
        it is a short backoff so failures do not retry every tick.
        """
        if task.cron_expression is not None:
            next_run = _calculate_next_run(task.cron_expression, None, base_time=now)
            return next_run if next_run is not None else self._backoff_next_run(now)
        return self._backoff_next_run(now)

    async def _tick(self, now: datetime) -> None:
        # Serialize ticks so a second rapid _tick cannot interleave between
        # listing due tasks and marking them in-flight.
        async with self._tick_lock:
            due = await self._scheduler_store.list_due_tasks(now)
            for task in due:
                # If the target session is already inside process_turn, skip this
                # tick and leave next_run_at untouched so the next tick retries.
                # Never await the session lock from inside the tick loop.
                lock_manager = getattr(self._orchestrator, "_lock_manager", None)
                if lock_manager is not None and lock_manager.is_locked(task.session_id):
                    logger.info(
                        "Scheduler skipping task %s: session %s lock is held",
                        task.id,
                        task.session_id,
                    )
                    continue

                # Mark in-flight before the long-running process_turn so the next
                # tick cannot re-list the same task while it is already dispatched.
                in_flight_next_run = self._in_flight_next_run(task, now)
                await self._scheduler_store.set_next_run_at(task.id, in_flight_next_run)
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
            await self._event_bus.publish(
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
                task.id, error=error, now=now, next_run_at=self._backoff_next_run(now)
            )
            return

        turn_error: str | None = None
        if task.task_type == "blocked_digest":
            if self._blocked_actions_digest is None:
                turn_error = "Blocked-actions digest service not configured"
            else:
                try:
                    text = await self._blocked_actions_digest.send_digest_for_task(task)
                    await self._deliver(task, text)
                except Exception as e:  # noqa: BLE001
                    logger.exception("Task %s failed during digest", task.id)
                    turn_error = str(e)
        elif task.task_type == "memory_maintenance_deterministic":
            if self._memory_maintenance is None or self._memory_maintenance_digest is None:
                turn_error = "Memory maintenance service not configured"
            else:
                try:
                    platform, platform_user = _parse_task_prompt(task.prompt)
                    await self._memory_maintenance.run_deterministic_pass(
                        platform, platform_user
                    )
                    text = await self._memory_maintenance_digest.send_digest_for_task(task)
                    await self._deliver(task, text)
                except Exception as e:  # noqa: BLE001
                    logger.exception("Task %s failed during memory maintenance", task.id)
                    turn_error = str(e)
        elif task.task_type == "memory_maintenance_llm":
            if self._memory_maintenance is None or self._memory_maintenance_digest is None:
                turn_error = "Memory maintenance service not configured"
            else:
                try:
                    platform, platform_user = _parse_task_prompt(task.prompt)
                    await self._memory_maintenance.run_llm_pass(platform, platform_user)
                    text = await self._memory_maintenance_digest.send_digest_for_task(task)
                    await self._deliver(task, text)
                except Exception as e:  # noqa: BLE001
                    logger.exception("Task %s failed during memory maintenance", task.id)
                    turn_error = str(e)
        else:
            user_message = Message(role="user", content=task.prompt)
            tick_token = scheduler_tick_active.set(True)
            try:
                turn = await self._orchestrator.process_turn(
                    session=session,
                    user_message=user_message,
                    respond_callback=lambda text: self._deliver(task, text),
                    system_prompt=self._system_prompt,
                    channel=Channel.SCHEDULER,
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

        # Compute next run: on error use a capped backoff, otherwise cron tasks
        # advance and one-shot tasks are disabled.
        if turn_error is not None:
            next_run = self._backoff_next_run(now)
        elif task.cron_expression is not None:
            calculated = _calculate_next_run(task.cron_expression, None, base_time=now)
            next_run = calculated if calculated is not None else self._backoff_next_run(now)
        else:
            next_run = None  # One-shot tasks don't repeat
        await self._scheduler_store.update_after_run(
            task.id, error=turn_error, now=now, next_run_at=next_run
        )

    async def _deliver(self, task: ScheduledTask, text: str) -> None:
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
