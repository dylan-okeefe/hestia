"""Egress API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import get_current_platform_user

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/egress")
async def list_egress(
    request: Request,
    domain: str | None = None,
    since: datetime | None = None,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List egress events with optional filtering."""
    caller_platform_user = get_current_platform_user(request)
    caller_role = None
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        user = await ctx.user_store.get_user(user_id)
        if user is not None:
            caller_role = user.role

    if caller_role == "admin":
        events = await ctx.trace_store.list_egress(domain=domain, since=since)
    elif caller_platform_user is not None:
        sessions = await ctx.session_store.list_sessions(
            limit=500, platform_user=caller_platform_user
        )
        session_ids = [s.id for s in sessions]
        events = await ctx.trace_store.list_egress(
            domain=domain, since=since, session_ids=session_ids
        )
    else:
        events = await ctx.trace_store.list_egress(domain=domain, since=since)

    return {
        "events": [
            {
                "id": e["id"],
                "session_id": e["session_id"],
                "url": e["url"],
                "domain": e["domain"],
                "status": e["status"],
                "size": e["size"],
                "created_at": e["created_at"],
            }
            for e in events
        ]
    }
