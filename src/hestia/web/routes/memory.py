"""Memory API routes for the Hestia dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from hestia.memory.store import Memory
from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import RequireOwner, get_current_platform_user

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


def _memory_to_dict(mem: Memory) -> dict[str, Any]:
    return {
        "id": mem.id,
        "content": mem.content,
        "tags": mem.tags,
        "created_at": mem.created_at.isoformat() if mem.created_at else None,
        "session_id": mem.session_id,
        "platform": mem.platform,
        "platform_user": mem.platform_user,
    }


@router.get("/memory")
async def list_memories(
    request: Request,
    platform: str | None = None,
    platform_user: str | None = None,
    limit: int = 20,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List memories, optionally filtered by platform user."""
    caller_platform_user = get_current_platform_user(request)
    caller_role = None
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        user = await ctx.user_store.get_user(user_id)
        if user is not None:
            caller_role = user.role

    if caller_platform_user is not None and caller_role != "admin":
        platform_user = caller_platform_user

    memories = await ctx.app.memory_store.list_memories(
        limit=limit,
        platform=platform,
        platform_user=platform_user,
    )
    return {"memories": [_memory_to_dict(m) for m in memories]}


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a memory by ID."""
    caller_platform_user = get_current_platform_user(request)
    if caller_platform_user is not None:
        mem = await ctx.app.memory_store.get(memory_id)
        if mem is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        if mem.platform_user is not None:
            await RequireOwner(mem.platform_user)(request, ctx)

    deleted = await ctx.app.memory_store.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}
