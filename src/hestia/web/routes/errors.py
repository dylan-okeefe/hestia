"""Centralized error and failures dashboard API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from hestia.web.context import WebContext, get_web_context

router = APIRouter()
_CTX_DEP = Depends(get_web_context)

# In-memory status tracking (resets on server restart)
_resolved_ids: set[str] = set()
_ignored_ids: set[str] = set()


async def _require_admin(request: Request, ctx: WebContext) -> None:
    """Check if the current web session has admin role."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await ctx.user_store.get_user(user_id)
    if user is None or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


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
    await _require_admin(request, ctx)
    errors: list[dict[str, Any]] = []

    # Workflow execution failures
    failed_executions = await ctx.execution_store.list_failed(limit=50)
    workflows = await ctx.workflow_store.list_workflows()
    workflow_names = {w.id: w.name for w in workflows}

    for ex in failed_executions:
        error_id = _build_error_id("workflow_execution", ex["id"])
        status = (
            "ignored"
            if error_id in _ignored_ids
            else "resolved"
            if error_id in _resolved_ids
            else "unresolved"
        )
        node_errors = [
            nr.get("error", "")
            for nr in ex.get("node_results", [])
            if nr.get("error")
        ]
        default_msg = f"Workflow execution {ex.get('status')}"
        message = "; ".join(node_errors) if node_errors else default_msg
        errors.append(
            {
                "id": error_id,
                "type": "workflow_execution",
                "source_id": ex["id"],
                "source_name": workflow_names.get(ex["workflow_id"], ex["workflow_id"]),
                "message": message,
                "created_at": ex["created_at"],
                "status": status,
            }
        )

    # Scheduler tasks with errors
    scheduler_tasks = await ctx.scheduler_store.list_tasks_with_errors(limit=50)
    for task in scheduler_tasks:
        error_id = _build_error_id("scheduler_task", task.id)
        status = (
            "ignored"
            if error_id in _ignored_ids
            else "resolved"
            if error_id in _resolved_ids
            else "unresolved"
        )
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
                "status": status,
            }
        )

    # Session turns with errors
    turns = await ctx.session_store.list_turns_with_errors(limit=50)
    for turn in turns:
        error_id = _build_error_id("session_turn", turn.id)
        status = (
            "ignored"
            if error_id in _ignored_ids
            else "resolved"
            if error_id in _resolved_ids
            else "unresolved"
        )
        session = await ctx.session_store.get_session(turn.session_id)
        source_name = (
            f"{session.platform}/{session.platform_user}"
            if session
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
                "status": status,
            }
        )

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
    """Mark an error as resolved."""
    await _require_admin(request, ctx)
    _parse_error_id(error_id)
    _resolved_ids.add(error_id)
    _ignored_ids.discard(error_id)
    return {"resolved": True}


@router.post("/errors/{error_id}/ignore")
async def ignore_error(
    error_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Mark an error as ignored."""
    await _require_admin(request, ctx)
    _parse_error_id(error_id)
    _ignored_ids.add(error_id)
    _resolved_ids.discard(error_id)
    return {"ignored": True}


@router.post("/errors/{error_id}/debug")
async def debug_error(
    error_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Return a debug prompt payload for the given error."""
    await _require_admin(request, ctx)
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
        import sqlalchemy as sa

        from hestia.persistence.schema import turns

        query = sa.select(turns).where(turns.c.id == source_id)
        async with ctx.session_store._db.engine.connect() as conn:
            result = await conn.execute(query)
            row = result.fetchone()
            if row:
                prompt_parts.append(f"Session: {row.session_id}")
                prompt_parts.append(f"State: {row.state}")
                prompt_parts.append(f"Error: {row.error}")
            else:
                prompt_parts.append("Turn record not found.")
    else:
        raise HTTPException(status_code=400, detail="Unknown error type")

    return {"prompt": "\n".join(prompt_parts)}
