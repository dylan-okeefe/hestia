"""FastAPI app factory for the Hestia dashboard."""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

_web_static = pathlib.Path(__file__).with_name("static")


def create_web_app() -> FastAPI:
    """Create and return the FastAPI application."""
    app = FastAPI(title="Hestia Dashboard", docs_url=None, redoc_url=None)
    app.mount("/", StaticFiles(directory=str(_web_static), html=True), name="static")
    return app
