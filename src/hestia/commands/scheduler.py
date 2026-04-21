"""Schedule-related command implementations."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from datetime import UTC, datetime

import click
import httpx

from hestia.app import CliAppContext, _require_scheduler_store
from hestia.core.types import ScheduledTask
from hestia.errors import HestiaError
from hestia.scheduler import Scheduler

from ._shared import _format_datetime

logger = logging.getLogger(__name__)


async def _cmd_schedule_add(
    app: CliAppContext,
    cron: str | None,
    fire_at_str: str | None,
    description: str | None,
    session_id: str | None,
    platform: str | None,
    platform_user: str | None,
    prompt: str,
) -> None:
    """Add a scheduled task."""
    if cron is not None and fire_at_str is not None:
        click.echo("Error: Cannot specify both --cron and --at", err=True)
        sys.exit(1)
    if cron is None and fire_at_str is None:
        click.echo("Error: Must specify either --cron or --at", err=True)
        sys.exit(1)
    if session_id is not None and (platform is not None or platform_user is not None):
        click.echo("Error: Cannot use --session-id with --platform or --platform-user", err=True)
        sys.exit(1)
    if (platform is not None) != (platform_user is not None):
        click.echo("Error: --platform and --platform-user must be used together", err=True)
        sys.exit(1)

    fire_at: datetime | None = None
    if fire_at_str is not None:
        try:
            fire_at = datetime.fromisoformat(fire_at_str)
        except ValueError:
            click.echo(
                "Error: Invalid datetime format "
                f"'{fire_at_str}'. Use ISO format: 2026-04-15T15:00:00",
                err=True,
            )
            sys.exit(1)
        if fire_at.tzinfo is None:
            fire_at = fire_at.replace(tzinfo=UTC)
        from hestia.core.clock import utcnow

        if fire_at < utcnow():
            click.echo(f"Error: Cannot schedule task in the past: {fire_at}", err=True)
            sys.exit(1)

    store = _require_scheduler_store(app)

    if session_id is not None:
        session = await app.session_store.get_session(session_id)
        if session is None:
            click.echo(f"Error: Session not found: {session_id}", err=True)
            sys.exit(1)
    elif platform is not None and platform_user is not None:
        session = await app.session_store.get_or_create_session(platform, platform_user)
    else:
        session = await app.session_store.get_or_create_session("cli", "default")

    try:
        task = await store.create_task(
            session_id=session.id,
            prompt=prompt,
            description=description,
            cron_expression=cron,
            fire_at=fire_at,
        )
        click.echo(f"Created task: {task.id}")
        click.echo(f"  Session: {task.session_id}")
        if task.cron_expression:
            click.echo(f"  Schedule: cron '{task.cron_expression}'")
        elif task.fire_at:
            click.echo(f"  Schedule: at {task.fire_at}")
        click.echo(f"  Next run: {task.next_run_at}")
    except (HestiaError, ValueError) as e:
        click.echo(f"Error creating task: {e}", err=True)
        sys.exit(1)


async def _cmd_schedule_list(app: CliAppContext) -> None:
    """List scheduled tasks."""
    store = _require_scheduler_store(app)
    tasks = await store.list_tasks_for_session(session_id=None, include_disabled=True)
    if not tasks:
        click.echo("No scheduled tasks.")
        return
    click.echo(f"{'ID':<20} {'Description':<25} {'Schedule':<20} {'Enabled':<8} {'Next Run'}")
    click.echo("-" * 95)
    for task in tasks:
        desc = (task.description or "")[:24]
        if task.cron_expression:
            sched = f"cron: {task.cron_expression[:16]}"
        elif task.fire_at:
            fire_at = task.fire_at
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(tzinfo=UTC)
            sched = f"at: {fire_at.astimezone().strftime('%Y-%m-%d %H:%M')[:16]}"
        else:
            sched = "unknown"
        enabled = "yes" if task.enabled else "no"
        if task.next_run_at:
            next_run_dt = task.next_run_at
            if next_run_dt.tzinfo is None:
                next_run_dt = next_run_dt.replace(tzinfo=UTC)
            next_run = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M")
        else:
            next_run = "-"
        click.echo(f"{task.id:<20} {desc:<25} {sched:<20} {enabled:<8} {next_run}")


async def _cmd_schedule_show(app: CliAppContext, task_id: str) -> None:
    """Show details of a scheduled task."""
    store = _require_scheduler_store(app)
    task = await store.get_task(task_id)
    if task is None:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    click.echo(f"ID:          {task.id}")
    click.echo(f"Session:     {task.session_id}")
    click.echo(f"Prompt:      {task.prompt}")
    if task.description:
        click.echo(f"Description: {task.description}")
    if task.cron_expression:
        click.echo(f"Schedule:    cron '{task.cron_expression}'")
    elif task.fire_at:
        click.echo(f"Schedule:    at {_format_datetime(task.fire_at)}")
    click.echo(f"Enabled:     {'yes' if task.enabled else 'no'}")
    click.echo(f"Next run:    {_format_datetime(task.next_run_at)}")
    click.echo(f"Last run:    {_format_datetime(task.last_run_at)}")
    if task.last_error:
        click.echo(f"Last error:  {task.last_error}")


async def _cmd_schedule_enable(app: CliAppContext, task_id: str) -> None:
    """Enable a scheduled task."""
    store = _require_scheduler_store(app)
    success = await store.set_enabled(task_id, True)
    if not success:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    click.echo(f"Task {task_id} enabled")


async def _cmd_schedule_run(app: CliAppContext, task_id: str) -> None:
    """Manually trigger a scheduled task."""
    store = _require_scheduler_store(app)
    task = await store.get_task(task_id)
    if task is None:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    orchestrator = app.make_orchestrator()

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[{task.id}] {text}")

    scheduler = Scheduler(
        scheduler_store=store,
        session_store=app.session_store,
        orchestrator=orchestrator,
        response_callback=response_callback,
        system_prompt=app.config.system_prompt,
    )
    try:
        await scheduler.run_now(task_id)
        click.echo(f"Task {task_id} executed successfully")
    except (HestiaError, httpx.HTTPError, OSError) as e:
        click.echo(f"Error running task: {e}", err=True)
        sys.exit(1)


async def _cmd_schedule_disable(app: CliAppContext, task_id: str) -> None:
    """Disable a scheduled task."""
    store = _require_scheduler_store(app)
    success = await store.disable_task(task_id)
    if not success:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    click.echo(f"Task {task_id} disabled")


async def _cmd_schedule_remove(app: CliAppContext, task_id: str) -> None:
    """Remove a scheduled task."""
    store = _require_scheduler_store(app)
    success = await store.delete_task(task_id)
    if not success:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    click.echo(f"Task {task_id} removed")


def _cmd_schedule_daemon(ctx: click.Context, tick_interval: float | None) -> None:
    """Run the scheduler daemon (blocks until Ctrl-C)."""
    app: CliAppContext = ctx.obj
    # Headless daemon — no confirmation callback
    app.set_confirm_callback(None)
    cfg = app.config
    tick = tick_interval if tick_interval is not None else cfg.scheduler.tick_interval_seconds

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[scheduler:{task.id}] {text}")

    async def _daemon() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)
        orchestrator = app.make_orchestrator()
        scheduler = Scheduler(
            scheduler_store=store,
            session_store=app.session_store,
            orchestrator=orchestrator,
            response_callback=response_callback,
            tick_interval_seconds=tick,
            system_prompt=app.config.system_prompt,
        )
        await scheduler.start()
        click.echo(f"Scheduler daemon started (tick={tick}s). Press Ctrl-C to stop.")
        try:
            while True:
                await asyncio.sleep(60)
                if app.config.reflection.enabled and app.reflection_scheduler is not None:
                    await app.reflection_scheduler.tick()
                if app.style_scheduler is not None:
                    await app.style_scheduler.tick()
        except asyncio.CancelledError:
            pass
        finally:
            click.echo("\nShutting down scheduler...")
            await scheduler.stop()

    def run_daemon() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        main_task = loop.create_task(_daemon())
        try:
            loop.run_until_complete(main_task)
        except KeyboardInterrupt:
            click.echo("\nReceived interrupt signal...")
            main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                loop.run_until_complete(main_task)
        finally:
            loop.run_until_complete(app.inference.close())
            loop.close()

    run_daemon()
