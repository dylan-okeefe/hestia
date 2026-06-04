"""Style profile API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import RequireOwner

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/{platform}/{user}")
async def get_style_profile(
    platform: str,
    user: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Get style profile for a user."""
    await RequireOwner(user)(request, ctx)
    profile = await ctx.style_store.get_profile_dict(platform, user)
    return {"platform": platform, "user": user, "profile": profile}


@router.delete("/{platform}/{user}/{metric}")
async def delete_style_metric(
    platform: str,
    user: str,
    metric: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a single style metric."""
    await RequireOwner(user)(request, ctx)
    deleted = await ctx.style_store.delete_metric(platform, user, metric)
    if not deleted:
        raise HTTPException(status_code=404, detail="Metric not found")
    return {"platform": platform, "user": user, "metric": metric, "deleted": True}
