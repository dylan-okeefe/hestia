"""Memory API routes for the Hestia dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from hestia.web.context import WebContext, get_web_context

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


def _memory_to_dict(mem: Any) -> dict[str, Any]:
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
    platform: str | None = None,
    platform_user: str | None = None,
    limit: int = 20,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List memories, optionally filtered by platform user."""
    memories = await ctx.app.memory_store.list_memories(
        limit=limit,
        platform=platform,
        platform_user=platform_user,
    )
    return {"memories": [_memory_to_dict(m) for m in memories]}


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a memory by ID."""
    deleted = await ctx.app.memory_store.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}
