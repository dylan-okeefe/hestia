"""FastAPI app factory for the Hestia dashboard."""

from __future__ import annotations

import pathlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hestia.web.routes import (
    audit,
    auth,
    browser_sessions,
    config,
    context_lab,
    doctor,
    egress,
    errors,
    health,
    memory,
    proposals,
    scheduler,
    sessions,
    style,
    tools,
    traces,
    users,
    webhooks,
    workflows,
)

_web_static = pathlib.Path(__file__).with_name("static")
_index_html = _web_static / "index.html"


def create_web_app() -> FastAPI:
    """Create and return the FastAPI application.

    Security note: authentication is configurable via WebConfig.auth_enabled.
    When enabled, Bearer token auth is enforced on all /api/* routes except
    /api/auth/* and /api/health. The dashboard binds to 127.0.0.1 by default.
    """
    app = FastAPI(title="Hestia Dashboard", docs_url=None, redoc_url=None)

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(sessions.router, prefix="/api/sessions")
    app.include_router(proposals.router, prefix="/api/proposals")
    app.include_router(style.router, prefix="/api/style")
    app.include_router(scheduler.router, prefix="/api/scheduler")
    app.include_router(traces.router, prefix="/api")
    app.include_router(doctor.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(egress.router, prefix="/api")
    app.include_router(config.router, prefix="/api")
    app.include_router(tools.router, prefix="/api")
    app.include_router(users.router, prefix="/api")
    app.include_router(errors.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(browser_sessions.router, prefix="/api")
    app.include_router(context_lab.router, prefix="/api")

    app.mount("/assets", StaticFiles(directory=str(_web_static / "assets")), name="assets")

    @app.get("/{path:path}")
    async def spa_catch_all(request: Request, path: str) -> FileResponse:
        """Serve index.html for all non-API routes (SPA routing)."""
        # API 404s should not return HTML
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(_index_html)

    return app
