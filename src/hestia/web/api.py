"""FastAPI app factory for the Hestia dashboard."""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hestia.web.routes import (
    audit,
    config,
    doctor,
    egress,
    proposals,
    scheduler,
    sessions,
    style,
    traces,
)

_web_static = pathlib.Path(__file__).with_name("static")


def create_web_app() -> FastAPI:
    """Create and return the FastAPI application."""
    app = FastAPI(title="Hestia Dashboard", docs_url=None, redoc_url=None)

    app.include_router(sessions.router, prefix="/api/sessions")
    app.include_router(proposals.router, prefix="/api/proposals")
    app.include_router(style.router, prefix="/api/style")
    app.include_router(scheduler.router, prefix="/api/scheduler")
    app.include_router(traces.router, prefix="/api")
    app.include_router(doctor.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(egress.router, prefix="/api")
    app.include_router(config.router, prefix="/api")

    app.mount("/", StaticFiles(directory=str(_web_static), html=True), name="static")
    return app
