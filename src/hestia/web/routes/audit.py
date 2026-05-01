"""Security audit API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from hestia.audit.checks import SecurityAuditor
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/audit")
async def run_audit(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Run security audit and return report."""
    auditor = SecurityAuditor(
        config=ctx.app.config,
        tool_registry=ctx.app.tool_registry,
        trace_store=ctx.trace_store,
    )
    report = await auditor.run_audit()
    return report.to_dict()
