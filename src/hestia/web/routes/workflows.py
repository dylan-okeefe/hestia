"""Workflow API routes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from hestia.workflows.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowVersion
from hestia.workflows.store import WorkflowStore
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


def _workflow_to_api(wf: Workflow) -> dict[str, Any]:
    """Serialize a Workflow to the API response shape expected by the frontend."""
    return {
        "id": wf.id,
        "name": wf.name,
        "trigger_type": wf.trigger_type,
        "last_edited_at": wf.updated_at.isoformat() if wf.updated_at else None,
        "active_version_id": None,  # populated by list/get where versions are loaded
    }


def _version_to_api(v: WorkflowVersion) -> dict[str, Any]:
    """Serialize a WorkflowVersion to the API response shape expected by the frontend."""
    return {
        "id": f"{v.workflow_id}:{v.version}",
        "workflow_id": v.workflow_id,
        "version_number": v.version,
        "nodes": [
            {
                "id": n.id,
                "type": n.type,
                "position": n.position,
                "data": {
                    "label": n.label,
                    **n.config,
                },
            }
            for n in v.nodes
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source_node_id,
                "target": e.target_node_id,
                "sourceHandle": e.source_handle,
                "targetHandle": e.target_handle,
            }
            for e in v.edges
        ],
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "activated_at": v.created_at.isoformat() if v.is_active and v.created_at else None,
    }


@router.get("/workflows")
async def list_workflows(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List all workflows."""
    workflows = await ctx.workflow_store.list_workflows()
    result = []
    for wf in workflows:
        api_wf = _workflow_to_api(wf)
        active = await ctx.workflow_store.get_active_version(wf.id)
        if active is not None:
            api_wf["active_version_id"] = f"{active.workflow_id}:{active.version}"
        result.append(api_wf)
    return {"workflows": result}


@router.post("/workflows")
async def create_workflow(
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Create a new workflow."""
    name = payload.get("name", "")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name is required and must be a string")

    wf = Workflow(
        id=str(uuid.uuid4()),
        name=name,
        description=payload.get("description", ""),
        trigger_type=payload.get("trigger_type", "manual"),
        trigger_config=payload.get("trigger_config", {}),
    )
    await ctx.workflow_store.save_workflow(wf)
    return _workflow_to_api(wf)


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Get a workflow by ID."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    api_wf = _workflow_to_api(workflow)
    active = await ctx.workflow_store.get_active_version(workflow_id)
    if active is not None:
        api_wf["active_version_id"] = f"{active.workflow_id}:{active.version}"
    return api_wf


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update workflow metadata."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if "name" in payload:
        name = payload["name"]
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail="name must be a non-empty string")
        workflow.name = name
    if "description" in payload:
        workflow.description = payload["description"]
    if "trigger_type" in payload:
        workflow.trigger_type = payload["trigger_type"]
    if "trigger_config" in payload:
        workflow.trigger_config = payload["trigger_config"]

    await ctx.workflow_store.save_workflow(workflow)
    return _workflow_to_api(workflow)


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
    return {"versions": [_version_to_api(v) for v in versions]}


@router.post("/workflows/{workflow_id}/versions")
async def create_version(
    workflow_id: str,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Save a new version for a workflow."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    existing = await ctx.workflow_store.list_versions(workflow_id)
    next_version = max((v.version for v in existing), default=0) + 1

    nodes_raw = payload.get("nodes", [])
    edges_raw = payload.get("edges", [])

    nodes = [
        WorkflowNode(
            id=n.get("id", str(uuid.uuid4())),
            type=n.get("type", "default"),
            label=n.get("data", {}).get("label", "") if isinstance(n.get("data"), dict) else "",
            config={k: v for k, v in n.get("data", {}).items() if k != "label"} if isinstance(n.get("data"), dict) else {},
            position=n.get("position", {"x": 0, "y": 0}),
        )
        for n in nodes_raw
    ]
    edges = [
        WorkflowEdge(
            id=e.get("id", str(uuid.uuid4())),
            source_node_id=e.get("source", ""),
            target_node_id=e.get("target", ""),
            source_handle=e.get("sourceHandle"),
            target_handle=e.get("targetHandle"),
        )
        for e in edges_raw
    ]

    version = WorkflowVersion(
        workflow_id=workflow_id,
        version=next_version,
        nodes=nodes,
        edges=edges,
    )
    await ctx.workflow_store.save_version(version)
    return _version_to_api(version)


@router.post("/workflows/{workflow_id}/versions/{version_id}/activate")
async def activate_version(
    workflow_id: str,
    version_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Activate a specific version of a workflow.

    version_id is expected to be "{workflow_id}:{version}" or just the version number.
    """
    # Parse version from version_id
    if ":" in version_id:
        _, version_str = version_id.rsplit(":", 1)
    else:
        version_str = version_id
    try:
        version_num = int(version_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid version ID")

    ok = await ctx.workflow_store.activate_version(workflow_id, version_num)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow or version not found")
    return {"activated": True, "version": version_num}
