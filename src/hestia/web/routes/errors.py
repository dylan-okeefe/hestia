"""Centralized error and failures dashboard API routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from hestia.core.types import Session
from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import require_admin

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


def _build_error_id(source_type: str, source_id: str) -> str:
    return f"{source_type}:{source_id}"


def _parse_error_id(error_id: str) -> tuple[str, str]:
    parts = error_id.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid error id format")
    return parts[0], parts[1]


@router.get("/errors")
async def list_errors(
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Aggregate last 50 errors from workflows, scheduler, and session turns."""
    await require_admin(request, ctx)

    # Ownership filtering (defensive: L180 restricts this route to admin,
    # so is_admin is effectively always True here. Kept for future
    # compatibility if auth restrictions are relaxed.)
    caller_user_id = getattr(request.state, "user_id", None)
    caller_platform_user = getattr(request.state, "platform_user", None)
    caller = await ctx.user_store.get_user(caller_user_id) if caller_user_id else None
    is_admin = caller is not None and caller.role == "admin"

    errors: list[dict[str, Any]] = []

    # Fetch error sources concurrently — these four calls are independent.
    # Batch session lookups below depend on the IDs returned here.
    assert ctx.turn_store is not None
    failed_executions, workflows, scheduler_tasks, turns = await asyncio.gather(
        ctx.execution_store.list_failed(limit=50),
        ctx.workflow_store.list_workflows(),
        ctx.scheduler_store.list_tasks_with_errors(limit=50),
        ctx.turn_store.list_turns_with_errors(limit=50),
    )

    workflow_names = {w.id: w.name for w in workflows}
    workflow_owners = {w.id: w.owner_id for w in workflows}

    for ex in failed_executions:
        wf_id = ex.get("workflow_id")
        if not is_admin and workflow_owners.get(wf_id or "") != caller_user_id:
            continue
        error_id = _build_error_id("workflow_execution", ex["id"])
        errors.append(
            {
                "id": error_id,
                "type": "workflow_execution",
                "source_id": ex["id"],
                "source_name": workflow_names.get(ex["workflow_id"], ex["workflow_id"]),
                "message": "; ".join(
                    nr.get("error", "")
                    for nr in ex.get("node_results", [])
                    if nr.get("error")
                ) or f"Workflow execution {ex.get('status')}",
                "created_at": ex["created_at"],
                "status": "unresolved",
            }
        )

    # Scheduler tasks with errors — session batch lookup depends on task IDs.
    task_session_ids = list({t.session_id for t in scheduler_tasks})
    task_sessions: dict[str, Session] = (
        await ctx.session_store.get_sessions_batch(task_session_ids)
        if task_session_ids
        else {}
    )
    task_session_owners = {s.id: s.platform_user for s in task_sessions.values()}

    for task in scheduler_tasks:
        if not is_admin and task_session_owners.get(task.session_id) != caller_platform_user:
            continue
        error_id = _build_error_id("scheduler_task", task.id)
        errors.append(
            {
                "id": error_id,
                "type": "scheduler_task",
                "source_id": task.id,
                "source_name": task.description or task.prompt[:50],
                "message": task.last_error or "Scheduler task error",
                "created_at": (
                    task.last_run_at.isoformat()
                    if task.last_run_at
                    else task.created_at.isoformat()
                ),
                "status": "unresolved",
            }
        )

    # Session turns with errors — session batch lookup depends on turn IDs.
    turn_session_ids = list({t.session_id for t in turns})
    turn_sessions: dict[str, Session] = (
        await ctx.session_store.get_sessions_batch(turn_session_ids)
        if turn_session_ids
        else {}
    )
    turn_session_owners = {s.id: s.platform_user for s in turn_sessions.values()}

    for turn in turns:
        if not is_admin and turn_session_owners.get(turn.session_id) != caller_platform_user:
            continue
        error_id = _build_error_id("session_turn", turn.id)
        source_name = (
            f"{turn_session_owners[turn.session_id]}/{turn.session_id}"
            if turn.session_id in turn_session_owners
            else turn.session_id
        )
        errors.append(
            {
                "id": error_id,
                "type": "session_turn",
                "source_id": turn.id,
                "source_name": source_name,
                "message": turn.error or "Session turn error",
                "created_at": turn.started_at.isoformat() if turn.started_at else None,
                "status": "unresolved",
            }
        )

    # Batch-fetch resolution statuses for all visible errors
    if errors and ctx.error_resolution_store is not None:
        error_ids = [e["id"] for e in errors]
        statuses = await ctx.error_resolution_store.list_statuses(error_ids)
        for error in errors:
            status = statuses.get(error["id"])
            if status:
                error["status"] = status

    # Sort by created_at descending and take last 50 overall
    errors.sort(key=lambda e: e["created_at"] or "", reverse=True)
    errors = errors[:50]

    return {"errors": errors}


@router.post("/errors/{error_id}/resolve")
async def resolve_error(
    error_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Mark an error as resolved. Persisted to SQLite."""
    await require_admin(request, ctx)
    _parse_error_id(error_id)
    current_user_id = getattr(request.state, "user_id", None)
    if ctx.error_resolution_store is not None:
        await ctx.error_resolution_store.set_status(
            error_id, "resolved", resolved_by=current_user_id
        )
    return {"resolved": True}


@router.post("/errors/{error_id}/ignore")
async def ignore_error(
    error_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Mark an error as ignored. Persisted to SQLite."""
    await require_admin(request, ctx)
    _parse_error_id(error_id)
    current_user_id = getattr(request.state, "user_id", None)
    if ctx.error_resolution_store is not None:
        await ctx.error_resolution_store.set_status(
            error_id, "ignored", resolved_by=current_user_id
        )
    return {"ignored": True}


@router.post("/errors/{error_id}/debug")
async def debug_error(
    error_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Return a debug prompt payload for the given error."""
    await require_admin(request, ctx)
    source_type, source_id = _parse_error_id(error_id)

    prompt_parts: list[str] = []
    prompt_parts.append(f"Debug {source_type.replace('_', ' ')} error:")

    if source_type == "workflow_execution":
        execution = await ctx.execution_store.get_execution(source_id)
        if execution:
            prompt_parts.append(f"Workflow: {execution.get('workflow_id')}")
            prompt_parts.append(f"Status: {execution.get('status')}")
            prompt_parts.append(f"Node results: {execution.get('node_results', [])}")
        else:
            prompt_parts.append("Execution record not found.")
    elif source_type == "scheduler_task":
        task = await ctx.scheduler_store.get_task(source_id)
        if task:
            prompt_parts.append(f"Task: {task.description or task.prompt}")
            prompt_parts.append(f"Error: {task.last_error}")
        else:
            prompt_parts.append("Task record not found.")
    elif source_type == "session_turn":
        assert ctx.turn_store is not None
        turn = await ctx.turn_store.get_turn(source_id)
        if turn is not None:
            session = await ctx.session_store.get_session(turn.session_id)
            prompt_parts.append(f"Session: {turn.session_id}")
            prompt_parts.append(f"State: {turn.state}")
            prompt_parts.append(f"Error: {turn.error}")
            if session is not None:
                prompt_parts.append(f"Platform user: {session.platform_user}")
        else:
            prompt_parts.append("Turn record not found.")
    else:
        raise HTTPException(status_code=400, detail="Unknown error type")

    return {"prompt": "\n".join(prompt_parts)}
