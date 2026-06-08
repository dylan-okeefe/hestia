"""Session API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import RequireOwner, get_current_platform_user

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


@router.get("")
async def list_sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    platform: str | None = Query(None),
    platform_user: str | None = Query(None),
    all: bool = Query(False),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List recent sessions."""
    caller_platform_user = get_current_platform_user(request)
    caller_role = None
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        user = await ctx.user_store.get_user(user_id)
        if user is not None:
            caller_role = user.role

    if caller_platform_user is not None and (not all or caller_role != "admin"):
        platform_user = caller_platform_user

    sessions = await ctx.session_store.list_sessions(
        limit=limit, platform=platform, platform_user=platform_user
    )
    session_ids = [s.id for s in sessions]
    turn_counts = await ctx.session_store.count_turns_for_sessions(session_ids)
    result = []
    for s in sessions:
        message_count = turn_counts.get(s.id, 0)
        result.append(
            {
                "id": s.id,
                "platform": s.platform,
                "platform_user": s.platform_user,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
                "state": s.state.value if s.state else None,
                "temperature": s.temperature.value if s.temperature else None,
                "message_count": message_count,
            }
        )
    return {"sessions": result}


@router.get("/{session_id}/turns")
async def get_turns(
    session_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List turns for a session."""
    session = await ctx.session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await RequireOwner(session.platform_user)(request, ctx)

    turns = await ctx.session_store.list_turns_for_session(session_id)
    return {
        "turns": [
            {
                "id": t.id,
                "session_id": t.session_id,
                "state": t.state.value if t.state else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "iterations": t.iterations,
                "error": t.error,
            }
            for t in turns
        ]
    }


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Get session metadata with turn transcript and actual messages."""
    session = await ctx.session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await RequireOwner(session.platform_user)(request, ctx)

    turns = await ctx.session_store.list_turns_for_session(session_id)
    messages = await ctx.session_store.get_messages(session_id)
    return {
        "session": {
            "id": session.id,
            "platform": session.platform,
            "platform_user": session.platform_user,
            "title": session.title,
            "started_at": session.started_at.isoformat() if session.started_at else None,
        },
        "turns": [
            {
                "id": t.id,
                "state": t.state.value if t.state else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "iterations": t.iterations,
                "error": t.error,
            }
            for t in turns
        ],
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }
