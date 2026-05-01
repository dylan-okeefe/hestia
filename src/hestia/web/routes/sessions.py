"""Session API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("")
async def list_sessions(
    limit: int = Query(50, ge=1, le=500),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List recent sessions."""
    sessions = await ctx.session_store.list_sessions(limit=limit)
    return {
        "sessions": [
            {
                "id": s.id,
                "platform": s.platform,
                "platform_user": s.platform_user,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
                "state": s.state.value if s.state else None,
                "temperature": s.temperature.value if s.temperature else None,
            }
            for s in sessions
        ]
    }


@router.get("/{session_id}/turns")
async def get_turns(
    session_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List turns for a session."""
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
