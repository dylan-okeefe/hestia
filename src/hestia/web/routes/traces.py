"""Trace and failure API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/traces")
async def list_traces(
    session_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List trace records."""
    traces = await ctx.trace_store.list_recent(session_id=session_id, limit=limit)
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
    class_filter: str | None = Query(None, alias="class"),
    limit: int = Query(50, ge=1, le=500),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List failure bundles."""
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
