"""Implementation for `hestia serve` — run all configured platform adapters and web dashboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import click
import uvicorn

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
        # Start a single scheduler for all background tasks (proposals, style
        # profiles, scheduled messages, memory maintenance). Platform runners are
        # told not to start their own scheduler since serve owns it.
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
            from hestia.platforms.matrix_adapter import MatrixAdapter
            from hestia.platforms.runners import run_matrix

            matrix_adapter = MatrixAdapter(config.matrix)
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
        if scheduler is not None:
            await scheduler.stop()
        await app.inference.close()
