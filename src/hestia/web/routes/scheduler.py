"""Scheduler API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/tasks")
async def list_tasks(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List all scheduled tasks."""
    tasks = await ctx.scheduler_store.list_tasks_for_session(
        session_id=None, include_disabled=True
    )
    return {
        "tasks": [
            {
                "id": t.id,
                "session_id": t.session_id,
                "prompt": t.prompt,
                "description": t.description,
                "cron_expression": t.cron_expression,
                "fire_at": t.fire_at.isoformat() if t.fire_at else None,
                "enabled": t.enabled,
                "notify": t.notify,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                "last_error": t.last_error,
            }
            for t in tasks
        ]
    }


@router.post("/tasks")
async def create_task(
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Create a new scheduled task."""
    prompt = payload.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    description = payload.get("description")
    cron_expression = payload.get("cron_expression")
    enabled = payload.get("enabled", True)
    session_id = payload.get("session_id", "default")

    task = await ctx.scheduler_store.create_task(
        session_id=session_id,
        prompt=prompt,
        description=description,
        cron_expression=cron_expression,
        enabled=enabled,
    )
    return {
        "id": task.id,
        "session_id": task.session_id,
        "prompt": task.prompt,
        "description": task.description,
        "cron_expression": task.cron_expression,
        "enabled": task.enabled,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
    }


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update an existing scheduled task."""
    task = await ctx.scheduler_store.update_task(
        task_id=task_id,
        prompt=payload.get("prompt"),
        description=payload.get("description"),
        cron_expression=payload.get("cron_expression"),
        enabled=payload.get("enabled"),
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "session_id": task.session_id,
        "prompt": task.prompt,
        "description": task.description,
        "cron_expression": task.cron_expression,
        "enabled": task.enabled,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
    }


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a scheduled task."""
    deleted = await ctx.scheduler_store.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


@router.post("/tasks/{task_id}/run")
async def run_task(
    task_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Trigger a task to run on the next scheduler tick."""
    task = await ctx.scheduler_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await ctx.scheduler_store.run_now(task_id)
    return {"id": task_id, "triggered": True}
