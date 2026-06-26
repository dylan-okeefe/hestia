"""Public health endpoint for process-level liveness checks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/health")
async def health_check(ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    """Return lightweight liveness status, including scheduler state."""
    scheduler = ctx.scheduler
    scheduler_running = scheduler.is_running if scheduler is not None else False
    return {
        "status": "ok" if scheduler_running else "degraded",
        "scheduler": {
            "running": scheduler_running,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
