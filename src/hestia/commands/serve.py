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

logger = logging.getLogger(__name__)


async def cmd_serve(app: AppContext, config: HestiaConfig) -> None:
    """Run Hestia with all configured platform adapters and the web dashboard."""
    tasks: list[asyncio.Task[Any]] = []
    original_close = app.inference.close

    async def _noop_close() -> None:
        pass

    # Prevent individual platform runners from closing inference;
    # we will close it centrally after everything stops.
    app.inference.close = _noop_close  # type: ignore[method-assign]

    try:
        if config.telegram.bot_token:
            from hestia.platforms.runners import run_telegram

            tasks.append(asyncio.create_task(run_telegram(app, config)))

        if config.matrix.access_token:
            from hestia.platforms.runners import run_matrix

            tasks.append(asyncio.create_task(run_matrix(app, config)))

        if config.web.enabled:
            from hestia.web.api import create_web_app
            from hestia.web.context import WebContext, set_web_context

            web_app = create_web_app()
            set_web_context(
                WebContext(
                    session_store=app.session_store,
                    proposal_store=app.proposal_store,
                    style_store=app.style_store,
                    scheduler_store=app.scheduler_store,
                    trace_store=app.trace_store,
                    failure_store=app.failure_store,
                    app=app,
                )
            )
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
        app.inference.close = original_close  # type: ignore[method-assign]
        await app.inference.close()
