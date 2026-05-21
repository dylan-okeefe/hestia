"""Style profile API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/{platform}/{user}")
async def get_style_profile(
    platform: str,
    user: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Get style profile for a user."""
    profile = await ctx.style_store.get_profile_dict(platform, user)
    return {"platform": platform, "user": user, "profile": profile}


@router.delete("/{platform}/{user}/{metric}")
async def delete_style_metric(
    platform: str,
    user: str,
    metric: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a single style metric."""
    deleted = await ctx.style_store.delete_metric(platform, user, metric)
    if not deleted:
        raise HTTPException(status_code=404, detail="Metric not found")
    return {"platform": platform, "user": user, "metric": metric, "deleted": True}
