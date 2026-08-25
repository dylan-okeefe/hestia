"""Memory API routes for the Hestia dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from hestia.memory.store import Memory
from hestia.memory.topics import Topic
from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import RequireOwner, get_current_platform_user

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


def _memory_to_dict(mem: Memory, topic_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": mem.id,
        "content": mem.content,
        "tags": mem.tags,
        "created_at": mem.created_at.isoformat() if mem.created_at else None,
        "session_id": mem.session_id,
        "platform": mem.platform,
        "platform_user": mem.platform_user,
        "is_global": mem.is_global,
        "is_pinned": mem.is_pinned,
        "is_active": mem.is_active,
        "deleted_at": mem.deleted_at.isoformat() if mem.deleted_at else None,
        "deleted_reason": mem.deleted_reason,
        "last_recalled_at": mem.last_recalled_at.isoformat() if mem.last_recalled_at else None,
        "topic_ids": topic_ids or [],
    }


def _topic_to_dict(topic: Any) -> dict[str, Any]:
    return {
        "id": topic.id,
        "platform": topic.platform,
        "platform_user": topic.platform_user,
        "name": topic.name,
        "created_at": topic.created_at.isoformat() if topic.created_at else None,
    }


async def _require_topic_access(
    request: Request, ctx: WebContext, topic_id: str
) -> Topic:
    """Fetch a topic and enforce ownership (SEC-007).

    Admins may access any topic; non-admins may only touch their own. An
    unauthenticated caller is rejected outright.
    """
    store = ctx.topic_store
    if store is None:
        raise HTTPException(status_code=503, detail="Topic store not available")
    topic = await store.get_topic_by_id(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")

    caller_platform_user = get_current_platform_user(request)
    if caller_platform_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    await RequireOwner(topic.platform_user)(request, ctx)
    return topic


async def _require_memory_owner(request: Request, ctx: WebContext, memory_id: str) -> Memory:
    """Fetch a memory and enforce ownership."""
    caller_platform_user = get_current_platform_user(request)
    mem = await ctx.app.memory_store.get(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    if caller_platform_user is not None and mem.platform_user is not None:
        await RequireOwner(mem.platform_user)(request, ctx)
    return mem


async def _caller_role(request: Request, ctx: WebContext) -> str | None:
    """Return the caller's role, or None if not authenticated."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return None
    user = await ctx.user_store.get_user(user_id)
    return user.role if user is not None else None


@router.get("/memory")
async def list_memories(
    request: Request,
    platform: str | None = None,
    platform_user: str | None = None,
    limit: int = 100,
    include_inactive: bool = False,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List memories with topic associations, optionally including soft-deleted."""
    caller_platform_user = get_current_platform_user(request)
    if caller_platform_user is not None and await _caller_role(request, ctx) != "admin":
        platform_user = caller_platform_user

    memories = await ctx.app.memory_store.list_memories(
        limit=limit,
        platform=platform,
        platform_user=platform_user,
        include_inactive=include_inactive,
    )
    memory_ids = [m.id for m in memories]
    topic_map = await ctx.app.memory_store.get_topic_ids_for_memories(memory_ids)
    return {
        "memories": [
            _memory_to_dict(m, topic_ids=topic_map.get(m.id, [])) for m in memories
        ]
    }


@router.put("/memory/{memory_id}")
async def update_memory(
    memory_id: str,
    request: Request,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update a memory's content, tags, global scope, and/or topic associations."""
    mem = await _require_memory_owner(request, ctx, memory_id)

    content = payload.get("content")
    tags = payload.get("tags")
    is_global = payload.get("is_global")
    topic_ids = payload.get("topic_ids")

    if tags is not None and not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list")
    if topic_ids is not None and not isinstance(topic_ids, list):
        raise HTTPException(status_code=400, detail="topic_ids must be a list")

    updated = await ctx.app.memory_store.update(
        memory_id,
        content=content,
        tags=tags,
        is_global=is_global,
        topic_ids=topic_ids,
        platform=mem.platform,
        platform_user=mem.platform_user,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found or not active")

    updated_mem = await ctx.app.memory_store.get(memory_id)
    assert updated_mem is not None
    topic_map = await ctx.app.memory_store.get_topic_ids_for_memories([memory_id])
    return {"memory": _memory_to_dict(updated_mem, topic_ids=topic_map.get(memory_id, []))}


@router.post("/memory/{memory_id}/pin")
async def pin_memory(
    memory_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Pin a memory."""
    mem = await _require_memory_owner(request, ctx, memory_id)
    # SEC-010: scope the mutation to the memory's owner explicitly.
    await ctx.app.memory_store.pin(
        memory_id,
        pinned=True,
        platform=mem.platform,
        platform_user=mem.platform_user,
    )
    return {"pinned": True}


@router.post("/memory/{memory_id}/unpin")
async def unpin_memory(
    memory_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Unpin a memory."""
    mem = await _require_memory_owner(request, ctx, memory_id)
    # SEC-010: scope the mutation to the memory's owner explicitly.
    await ctx.app.memory_store.pin(
        memory_id,
        pinned=False,
        platform=mem.platform,
        platform_user=mem.platform_user,
    )
    return {"pinned": False}


@router.post("/memory/{memory_id}/soft-delete")
async def soft_delete_memory(
    memory_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Soft-delete a memory."""
    mem = await _require_memory_owner(request, ctx, memory_id)
    deleted = await ctx.app.memory_store.soft_delete(
        memory_id,
        platform=mem.platform,
        platform_user=mem.platform_user,
        reason="user",
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}


@router.post("/memory/{memory_id}/restore")
async def restore_memory(
    memory_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Restore a soft-deleted memory."""
    mem = await _require_memory_owner(request, ctx, memory_id)
    restored = await ctx.app.memory_store.restore(
        memory_id,
        platform=mem.platform,
        platform_user=mem.platform_user,
    )
    if not restored:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"restored": True}


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Permanently delete a memory by ID."""
    mem = await _require_memory_owner(request, ctx, memory_id)
    deleted = await ctx.app.memory_store.delete(
        memory_id,
        platform=mem.platform,
        platform_user=mem.platform_user,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}


@router.get("/topics")
async def list_topics(
    request: Request,
    platform: str | None = None,
    platform_user: str | None = None,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List user-named topics for the current identity."""
    caller_platform_user = get_current_platform_user(request)
    if caller_platform_user is not None and await _caller_role(request, ctx) != "admin":
        platform_user = caller_platform_user

    if platform is None or platform_user is None:
        raise HTTPException(status_code=400, detail="platform and platform_user required")

    store = ctx.topic_store
    if store is None:
        raise HTTPException(status_code=503, detail="Topic store not available")

    topics = await store.list_topics(platform, platform_user)
    return {"topics": [_topic_to_dict(t) for t in topics]}


@router.post("/topics")
async def create_topic(
    request: Request,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Create a new topic for the current identity."""
    caller_platform_user = get_current_platform_user(request)
    caller_role = await _caller_role(request, ctx)

    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Topic name is required")
    if name.startswith("room:"):
        raise HTTPException(status_code=400, detail="Reserved topic prefix")

    platform = payload.get("platform")
    platform_user = payload.get("platform_user")
    if caller_platform_user is not None and caller_role != "admin":
        platform_user = caller_platform_user

    if platform is None or platform_user is None:
        raise HTTPException(status_code=400, detail="platform and platform_user required")

    store = ctx.topic_store
    if store is None:
        raise HTTPException(status_code=503, detail="Topic store not available")

    topic = await store.get_or_create_topic(platform, platform_user, name)
    return {"topic": _topic_to_dict(topic)}


@router.put("/topics/{topic_id}")
async def rename_topic(
    topic_id: str,
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Rename a topic (SEC-007: owner or admin only)."""
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Topic name is required")
    if name.startswith("room:"):
        raise HTTPException(status_code=400, detail="Reserved topic prefix")

    await _require_topic_access(request, ctx, topic_id)
    store = ctx.topic_store
    if store is None:
        raise HTTPException(status_code=503, detail="Topic store not available")

    topic = await store.rename_topic(topic_id, name)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"topic": _topic_to_dict(topic)}


@router.delete("/topics/{topic_id}")
async def delete_topic(
    topic_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a topic (SEC-007: owner or admin only)."""
    await _require_topic_access(request, ctx, topic_id)
    store = ctx.topic_store
    if store is None:
        raise HTTPException(status_code=503, detail="Topic store not available")

    deleted = await store.delete_topic(topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"deleted": True}


@router.get("/topics/{topic_id}/conversations")
async def list_topic_conversations(
    topic_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List conversations subscribed to a topic (SEC-007: owner/admin)."""
    await _require_topic_access(request, ctx, topic_id)
    store = ctx.topic_store
    if store is None:
        raise HTTPException(status_code=503, detail="Topic store not available")

    conversations = await store.list_topic_conversations(topic_id)
    return {"conversations": conversations}
