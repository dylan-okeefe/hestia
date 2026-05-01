"""Doctor (health check) API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from hestia.doctor import run_checks
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/doctor")
async def doctor_check(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Run health checks and return results."""
    results = await run_checks(ctx.app)
    return {
        "checks": [
            {"name": r.name, "ok": r.ok, "detail": r.detail}
            for r in results
        ]
    }
