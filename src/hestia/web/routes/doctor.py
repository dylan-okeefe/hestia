"""Doctor (health check) API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from hestia.doctor import run_checks
from hestia.web.cache import InMemoryCache
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)

_doctor_cache = InMemoryCache()


@router.get("/doctor")
async def doctor_check(
    max_age_seconds: int = 60,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Run health checks and return results."""
    cached = _doctor_cache.get("doctor", max_age_seconds)
    if cached is not None:
        return {**cached, "cached": True}

    results = await run_checks(ctx.app)
    data = {
        "checks": [
            {"name": r.name, "ok": r.ok, "detail": r.detail}
            for r in results
        ],
        "cached": False,
    }
    _doctor_cache.set("doctor", data)
    return data
