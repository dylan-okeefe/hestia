"""Security audit API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from hestia.audit.checks import SecurityAuditor
from hestia.web.cache import InMemoryCache
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)

_audit_cache = InMemoryCache()


@router.get("/audit")
async def run_audit(
    max_age_seconds: int = 300,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Run security audit and return report."""
    cached = _audit_cache.get("audit", max_age_seconds)
    if cached is not None:
        return {**cached, "cached": True}

    auditor = SecurityAuditor(
        config=ctx.app.config,
        tool_registry=ctx.app.tool_registry,
        trace_store=ctx.trace_store,
    )
    report = await auditor.run_audit()
    data = {**report.to_dict(), "cached": False}
    _audit_cache.set("audit", data)
    return data
