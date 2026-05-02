"""FastAPI app factory for the Hestia dashboard."""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hestia.web.routes import (
    audit,
    auth,
    config,
    doctor,
    egress,
    proposals,
    scheduler,
    sessions,
    style,
    traces,
    workflows,
)

_web_static = pathlib.Path(__file__).with_name("static")


def create_web_app() -> FastAPI:
    """Create and return the FastAPI application.

    Security note: authentication is configurable via WebConfig.auth_enabled.
    When enabled, Bearer token auth is enforced on all /api/* routes except
    /api/auth/*. The dashboard binds to 127.0.0.1 by default.
    """
    app = FastAPI(title="Hestia Dashboard", docs_url=None, redoc_url=None)

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
    app.include_router(workflows.router, prefix="/api")

    app.mount("/", StaticFiles(directory=str(_web_static), html=True), name="static")
    return app
