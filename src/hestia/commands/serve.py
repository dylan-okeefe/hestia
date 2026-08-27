"""Implementation for `hestia serve` — run all configured platform adapters and web dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import click
import sqlalchemy as sa
import uvicorn

import hestia
from hestia.app import AppContext
from hestia.config import HestiaConfig
from hestia.persistence.scheduler import SchedulerStore
from hestia.scheduler import Scheduler
from hestia.scheduler.cleanup import run_error_resolution_cleanup, run_maintenance_trace_cleanup

logger = logging.getLogger(__name__)


async def cmd_serve(app: AppContext, config: HestiaConfig) -> None:
    """Run Hestia with all configured platform adapters and the web dashboard."""
    await app.bootstrap_db()
    # BUG-036: executions stuck RUNNING from a previous crash become failed
    # rows so the dashboard reflects reality.
    swept = await app.execution_store.fail_stale_running()
    if swept:
        click.echo(f"Marked {swept} interrupted workflow execution(s) as failed.")
    await app.start_trigger_registry()
    tasks: list[asyncio.Task[Any]] = []

    adapters: dict[str, Any] = {}

    try:
        # Start the task-store scheduler. Proposals and style profiles are
        # NOT this scheduler - their tick loops are wired separately below
        # (see tick_tasks); this one covers cron tasks and scheduled
        # messages. Platform runners are told not to start their own since
        # serve owns scheduling.
        scheduler: Scheduler | None = None
        from hestia.platforms.runners import make_serve_scheduler_callback

        scheduler = Scheduler(
            scheduler_store=SchedulerStore(app.db),
            session_store=app.session_store,
            orchestrator=app.make_orchestrator(),
            response_callback=make_serve_scheduler_callback(adapters, app.session_store),
            tick_interval_seconds=config.scheduler.tick_interval_seconds,
            system_prompt=config.system_prompt,
            event_bus=app.event_bus,
            blocked_actions_digest=app.blocked_actions_digest,
            memory_maintenance=app.memory_maintenance,
            memory_maintenance_digest=app.memory_maintenance_digest,
        )
        await scheduler.start()

        # Reflection and style ticks: each scheduler owns its one tick site
        # (tick_loop); serve just runs it. Gaps between ticks use the same
        # 60s cadence the daemon used.
        tick_tasks: list[asyncio.Task[None]] = []
        # Safety (R4-5): _is_due only fires within 2 minutes of the cron
        # match, so the tick interval MUST stay below that or reflection
        # silently never fires. Warn rather than clamp - operators who
        # raised it should hear why their reflection stopped.
        tick_interval = config.scheduler.tick_interval_seconds
        if tick_interval >= 120:
            click.echo(
                click.style(
                    f"Warning: scheduler.tick_interval_seconds={tick_interval} "
                    "is >= the 2-minute reflection/style due window - "
                    "those ticks may silently never fire.",
                    fg="yellow",
                ),
                err=True,
            )

        reflection_scheduler = (
            app.reflection_scheduler if config.reflection.enabled else None
        )
        if reflection_scheduler is not None:
            logger.info("Starting reflection tick loop (interval=%ss)", tick_interval)
            tick_tasks.append(
                asyncio.create_task(
                    reflection_scheduler.tick_loop(interval_seconds=tick_interval)
                )
            )

        style_scheduler = app.style_scheduler
        if style_scheduler is not None:
            logger.info("Starting style tick loop (interval=%ss)", tick_interval)
            tick_tasks.append(
                asyncio.create_task(
                    style_scheduler.tick_loop(interval_seconds=tick_interval)
                )
            )

        # Startup health surface (#60): one line that would have caught both the
        # stale process and the disabled config without a manual DB query.
        memory_count = await app.memory_store.count()
        proposal_status_counts = await app.proposal_store.count_by_status()
        proposal_count = sum(proposal_status_counts.values())
        async with app.db.engine.connect() as conn:
            last_memory_at = (
                await conn.execute(sa.text("SELECT MAX(created_at) FROM memory"))
            ).scalar()
            last_session_at = (
                await conn.execute(sa.text("SELECT MAX(last_active_at) FROM sessions"))
            ).scalar()
        click.echo(
            f"Hestia {hestia.__version__} serve started | "
            f"reflection={'on' if config.reflection.enabled else 'off'} | "
            f"style={'on' if config.style.enabled else 'off'} | "
            f"memories={memory_count} | "
            f"proposals={proposal_count} | "
            f"last_memory={last_memory_at or 'never'} | "
            f"last_session={last_session_at or 'never'}"
        )

        if config.telegram.bot_token:
            from hestia.platforms.runners import run_telegram
            from hestia.platforms.telegram_adapter import TelegramAdapter

            telegram_adapter = TelegramAdapter(config.telegram)
            adapters["telegram"] = telegram_adapter
            tasks.append(
                asyncio.create_task(
                    run_telegram(
                        app,
                        config,
                        adapter=telegram_adapter,
                        start_scheduler=False,
                        close_inference=False,
                    )
                )
            )

        if config.matrix.access_token:
            # L247 5B-1 + review P7/P8: decide on the structured platform
            # key, never the message text. Gaps are already printed once by
            # make_app's startup report; this branch only needs the decision.
            from hestia.app import platform_credential_gaps
            from hestia.platforms.matrix_adapter import MatrixAdapter
            from hestia.platforms.runners import run_matrix

            matrix_broken = any(
                gap.platform == "matrix"
                for gap in platform_credential_gaps(config)
            )
            matrix_adapter = (
                None if matrix_broken else MatrixAdapter(config.matrix)
            )
            if matrix_adapter is not None:
                adapters["matrix"] = matrix_adapter
                tasks.append(
                    asyncio.create_task(
                        run_matrix(
                            app,
                            config,
                            adapter=matrix_adapter,
                            start_scheduler=False,
                            close_inference=False,
                        )
                    )
                )

        if config.email.imap_host:
            from hestia.email.adapter import EmailAdapter
            from hestia.platforms.email_inbound import run_email_poller

            email_adapter = EmailAdapter(config.email)
            tasks.append(
                asyncio.create_task(run_email_poller(app, email_adapter))
            )

        if config.web.enabled:
            from hestia.tools.browser.session_store import BrowserSessionStore
            from hestia.web.api import create_web_app
            from hestia.web.auth import AuthManager, add_auth_middleware
            from hestia.web.browser_stream import SessionStreamManager
            from hestia.web.context import WebContext, set_web_context

            web_app = create_web_app()
            auth_manager = AuthManager(
                adapters=adapters, config=config.web, user_store=app.user_store
            )
            browser_session_store = BrowserSessionStore()
            set_web_context(
                WebContext(
                    session_store=app.session_store,
                    message_store=app.message_store,
                    turn_store=app.turn_store,
                    handoff_service=app.handoff_service,
                    proposal_store=app.proposal_store,
                    style_store=app.style_store,
                    scheduler_store=app.scheduler_store,
                    trace_store=app.trace_store,
                    failure_store=app.failure_store,
                    workflow_store=app.workflow_store,
                    execution_store=app.execution_store,
                    error_resolution_store=app.error_resolution_store,
                    app=app,
                    auth_manager=auth_manager,
                    trigger_registry=app.trigger_registry,
                    user_store=app.user_store,
                    browser_session_store=browser_session_store,
                    stream_manager=SessionStreamManager(browser_session_store),
                    scheduler=scheduler,
                    topic_store=app.topic_store,
                )
            )
            add_auth_middleware(web_app, auth_manager, config.web)
            uvicorn_config = uvicorn.Config(
                web_app,
                host=config.web.host,
                port=config.web.port,
                log_level="info",
            )
            server = uvicorn.Server(uvicorn_config)
            click.echo(
                f"Dashboard available at http://{config.web.host}:{config.web.port}"
            )
            tasks.append(asyncio.create_task(server.serve()))
            tasks.append(
                asyncio.create_task(
                    run_error_resolution_cleanup(app.error_resolution_store)
                )
            )
            tasks.append(
                asyncio.create_task(
                    run_maintenance_trace_cleanup(app.maintenance_trace_store)
                )
            )

        if not tasks:
            click.echo("No platforms or web server configured. Exiting.")
            return

        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for t in tick_tasks:
            t.cancel()
        if tick_tasks:
            await asyncio.gather(*tick_tasks, return_exceptions=True)
        if scheduler is not None:
            await scheduler.stop()
        await app.inference.close()
