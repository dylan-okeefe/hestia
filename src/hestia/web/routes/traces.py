"""Trace and failure API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import RequireOwner, get_current_platform_user

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/traces")
async def list_traces(
    request: Request,
    session_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List trace records."""
    caller_platform_user = get_current_platform_user(request)
    caller_role = None
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        user = await ctx.user_store.get_user(user_id)
        if user is not None:
            caller_role = user.role

    if session_id is not None:
        session = await ctx.session_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        await RequireOwner(session.platform_user)(request, ctx)
        traces = await ctx.trace_store.list_recent(session_id=session_id, limit=limit)
    else:
        if caller_role == "admin":
            traces = await ctx.trace_store.list_recent(limit=limit)
        elif caller_platform_user is not None:
            sessions = await ctx.session_store.list_sessions(
                limit=500, platform_user=caller_platform_user
            )
            session_ids = [s.id for s in sessions]
            traces = await ctx.trace_store.list_recent(
                session_ids=session_ids, limit=limit
            )
        else:
            traces = await ctx.trace_store.list_recent(limit=limit)

    return {
        "traces": [
            {
                "id": t.id,
                "session_id": t.session_id,
                "turn_id": t.turn_id,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "ended_at": t.ended_at.isoformat() if t.ended_at else None,
                "user_input_summary": t.user_input_summary,
                "tools_called": t.tools_called,
                "tool_call_count": t.tool_call_count,
                "delegated": t.delegated,
                "outcome": t.outcome,
                "artifact_handles": t.artifact_handles,
                "prompt_tokens": t.prompt_tokens,
                "completion_tokens": t.completion_tokens,
                "reasoning_tokens": t.reasoning_tokens,
                "total_duration_ms": t.total_duration_ms,
            }
            for t in traces
        ]
    }


@router.get("/failures")
async def list_failures(
    request: Request,
    session_id: str | None = Query(None),
    class_filter: str | None = Query(None, alias="class"),
    limit: int = Query(50, ge=1, le=500),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List failure bundles."""
    caller_platform_user = get_current_platform_user(request)
    caller_role = None
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        user = await ctx.user_store.get_user(user_id)
        if user is not None:
            caller_role = user.role

    if session_id is not None:
        session = await ctx.session_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        await RequireOwner(session.platform_user)(request, ctx)
        failures = await ctx.failure_store.list_recent(
            failure_class=class_filter, limit=limit, session_id=session_id
        )
    else:
        if caller_role == "admin":
            failures = await ctx.failure_store.list_recent(
                failure_class=class_filter, limit=limit
            )
        elif caller_platform_user is not None:
            sessions = await ctx.session_store.list_sessions(
                limit=500, platform_user=caller_platform_user
            )
            session_ids = [s.id for s in sessions]
            failures = await ctx.failure_store.list_recent(
                failure_class=class_filter, limit=limit, session_ids=session_ids
            )
        else:
            failures = await ctx.failure_store.list_recent(
                failure_class=class_filter, limit=limit
            )

    return {
        "failures": [
            {
                "id": f.id,
                "session_id": f.session_id,
                "turn_id": f.turn_id,
                "failure_class": f.failure_class,
                "severity": f.severity,
                "error_message": f.error_message,
                "tool_chain": f.tool_chain,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in failures
        ]
    }
