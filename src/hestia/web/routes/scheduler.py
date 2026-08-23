"""Scheduler API routes."""

from __future__ import annotations

from typing import Any

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import get_current_platform_user

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


class TaskCreate(BaseModel):
    """Payload for creating a scheduled task."""

    prompt: str
    description: str | None = None
    cron_expression: str | None = None
    enabled: bool = True
    notify: bool = False

    @field_validator("cron_expression")
    @classmethod
    def _validate_cron(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                croniter(v)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid cron expression: {exc}") from exc
        return v


class TaskUpdate(BaseModel):
    """Payload for updating a scheduled task."""

    prompt: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    notify: bool | None = None

    @field_validator("cron_expression")
    @classmethod
    def _validate_cron(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                croniter(v)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid cron expression: {exc}") from exc
        return v


@router.get("/tasks")
async def list_tasks(
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List scheduled tasks scoped to the caller."""
    caller_platform_user = getattr(request.state, "platform_user", None)
    session_id: str | None = None

    if caller_platform_user is not None:
        caller_user_id = getattr(request.state, "user_id", None)
        if caller_user_id is not None:
            caller = await ctx.user_store.get_user(caller_user_id)
            if caller is None or caller.role != "admin":
                session_id = caller_platform_user
        else:
            session_id = caller_platform_user

    tasks = await ctx.scheduler_store.list_tasks_for_session(
        session_id=session_id, include_disabled=True
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
    request: Request,
    payload: TaskCreate,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Create a new scheduled task."""
    session_id = get_current_platform_user(request) or "default"

    task = await ctx.scheduler_store.create_task(
        session_id=session_id,
        prompt=payload.prompt,
        description=payload.description,
        cron_expression=payload.cron_expression,
        enabled=payload.enabled,
        notify=payload.notify,
    )
    return {
        "id": task.id,
        "session_id": task.session_id,
        "prompt": task.prompt,
        "description": task.description,
        "cron_expression": task.cron_expression,
        "enabled": task.enabled,
        "notify": task.notify,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
    }


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str,
    request: Request,
    payload: TaskUpdate,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update an existing scheduled task."""
    task = await ctx.scheduler_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    caller_platform_user = get_current_platform_user(request)
    caller_is_admin = getattr(request.state, "role", None) == "admin"
    if (
        caller_platform_user is not None
        and not caller_is_admin
        and task.session_id != caller_platform_user
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    update_kwargs: dict[str, Any] = {
        "task_id": task_id,
        "prompt": payload.prompt,
        "description": payload.description,
        "cron_expression": payload.cron_expression,
        "enabled": payload.enabled,
    }
    if payload.notify is not None:
        update_kwargs["notify"] = payload.notify
    task = await ctx.scheduler_store.update_task(**update_kwargs)
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
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a scheduled task."""
    task = await ctx.scheduler_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    caller_platform_user = get_current_platform_user(request)
    caller_is_admin = getattr(request.state, "role", None) == "admin"
    if (
        caller_platform_user is not None
        and not caller_is_admin
        and task.session_id != caller_platform_user
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    deleted = await ctx.scheduler_store.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


@router.post("/tasks/{task_id}/run")
async def run_task(
    task_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Trigger a task to run on the next scheduler tick."""
    task = await ctx.scheduler_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    caller_platform_user = get_current_platform_user(request)
    caller_is_admin = getattr(request.state, "role", None) == "admin"
    if (
        caller_platform_user is not None
        and not caller_is_admin
        and task.session_id != caller_platform_user
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    await ctx.scheduler_store.run_now(task_id)
    return {"id": task_id, "triggered": True}
