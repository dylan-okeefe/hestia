"""Egress API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/egress")
async def list_egress(
    domain: str | None = None,
    since: datetime | None = None,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List egress events with optional filtering."""
    events = await ctx.trace_store.list_egress(domain=domain, since=since)
    # list_egress returns list[dict[str, Any]] (not dataclass objects)
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
