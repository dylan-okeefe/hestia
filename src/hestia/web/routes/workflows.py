"""Workflow API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/workflows")
async def list_workflows(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List all workflows."""
    workflows = await ctx.workflow_store.list_workflows()
    return {
        "workflows": [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "active_version": w.active_version,
            }
            for w in workflows
        ]
    }


@router.post("/workflows")
async def create_workflow(
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Create a new workflow with an initial version."""
    name = payload.get("name", "")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name is required and must be a string")
    description = payload.get("description")
    definition = payload.get("definition")
    workflow = await ctx.workflow_store.create_workflow(
        name=name,
        description=description,
        definition=definition,
    )
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "active_version": workflow.active_version,
    }


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Get a workflow by ID, including its active version definition."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    active_version = await ctx.workflow_store.get_active_version(workflow_id)
    result: dict[str, Any] = {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "active_version": workflow.active_version,
    }
    if active_version is not None:
        result["definition"] = active_version.definition
    return result


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update workflow metadata."""
    name = payload.get("name")
    description = payload.get("description")
    if name is not None and (not isinstance(name, str) or not name):
        raise HTTPException(status_code=400, detail="name must be a non-empty string")
    workflow = await ctx.workflow_store.update_workflow(
        workflow_id, name=name, description=description
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "active_version": workflow.active_version,
    }


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a workflow and all its versions."""
    deleted = await ctx.workflow_store.delete_workflow(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"deleted": True}


@router.get("/workflows/{workflow_id}/versions")
async def list_versions(
    workflow_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List all versions for a workflow."""
    versions = await ctx.workflow_store.list_versions(workflow_id)
    return {
        "versions": [
            {
                "id": v.id,
                "workflow_id": v.workflow_id,
                "version": v.version,
                "definition": v.definition,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "is_active": v.is_active,
            }
            for v in versions
        ]
    }


@router.post("/workflows/{workflow_id}/versions")
async def create_version(
    workflow_id: str,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Save a new version for a workflow."""
    definition = payload.get("definition")
    if definition is None:
        raise HTTPException(status_code=400, detail="definition is required")
    version = await ctx.workflow_store.create_version(workflow_id, definition)
    return {
        "id": version.id,
        "workflow_id": version.workflow_id,
        "version": version.version,
        "definition": version.definition,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "is_active": version.is_active,
    }


@router.post("/workflows/{workflow_id}/versions/{version}/activate")
async def activate_version(
    workflow_id: str,
    version: int,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Activate a specific version of a workflow."""
    ok = await ctx.workflow_store.activate_version(workflow_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow or version not found")
    return {"activated": True, "version": version}
