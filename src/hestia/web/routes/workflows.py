"""Workflow API routes."""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from hestia.web.context import WebContext, get_web_context
from hestia.workflows.executor import WorkflowExecutor
from hestia.workflows.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowVersion


async def _require_workflow_access(
    request: Request,
    ctx: WebContext,
    workflow: Workflow,
) -> None:
    """Raise 403 if caller is not the workflow owner and not an admin."""
    caller_platform_user = getattr(request.state, "platform_user", None)
    if caller_platform_user is None:
        auth_enabled = getattr(ctx.app.config.features.web, "auth_enabled", True)
        if auth_enabled:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return
    if caller_platform_user == workflow.owner_id:
        return

    caller_user_id = getattr(request.state, "user_id", None)
    if caller_user_id is not None:
        caller = await ctx.user_store.get_user(caller_user_id)
        if caller is not None and caller.role == "admin":
            return

    raise HTTPException(status_code=403, detail="Access denied")


router = APIRouter()

_CTX_DEP = Depends(get_web_context)


_TRUST_LEVELS = {"paranoid", "prompt_on_mobile", "household", "developer"}

REDACTED_SECRET = "__redacted__"
"""Sentinel value exposed in place of a real webhook secret."""


def _redact_trigger_config(trigger_config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *trigger_config* with the webhook secret redacted.

    Exposes ``has_secret`` so the UI can indicate whether a secret is set
    without revealing its value.
    """
    redacted = dict(trigger_config)
    has_secret = bool(redacted.get("secret"))
    if "secret" in redacted:
        redacted["secret"] = REDACTED_SECRET
    redacted["has_secret"] = has_secret
    return redacted


_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|apikey|secret|token|password|passwd|authorization)",
    re.IGNORECASE,
)


def _redact_node_config(config: dict[str, Any]) -> dict[str, Any]:
    """SEC-014: mask secret-looking keys in node configs before returning
    them through the versions/workflow APIs. Values are replaceable — the
    stored version keeps the real content server-side."""
    redacted: dict[str, Any] = {}

    def _walk(src: dict[str, Any], dst: dict[str, Any]) -> None:
        for key, value in src.items():
            if isinstance(value, dict):
                nested: dict[str, Any] = {}
                _walk(value, nested)
                dst[key] = nested
            elif isinstance(key, str) and _SECRET_KEY_RE.search(key):
                if value:
                    dst[key] = "__redacted__"
                else:
                    dst[key] = value
            else:
                dst[key] = value

    _walk(config, redacted)
    return redacted


def _workflow_to_api(wf: Workflow, redact_secret: bool = True) -> dict[str, Any]:
    """Serialize a Workflow to the API response shape expected by the frontend."""
    trigger_config = _redact_trigger_config(wf.trigger_config) if redact_secret else dict(wf.trigger_config)
    if "has_secret" not in trigger_config:
        trigger_config["has_secret"] = bool(wf.trigger_config.get("secret"))
    return {
        "id": wf.id,
        "name": wf.name,
        "trigger_type": wf.trigger_type,
        "trigger_config": trigger_config,
        "owner_id": wf.owner_id,
        "trust_level": wf.trust_level,
        "last_edited_at": wf.updated_at.isoformat() if wf.updated_at else None,
        "active_version_id": None,  # populated by list/get where versions are loaded
    }


async def _is_admin(request: Request, ctx: WebContext) -> bool:
    """Return True if the authenticated caller is an admin."""
    caller_user_id = getattr(request.state, "user_id", None)
    if caller_user_id is None:
        return False
    caller = await ctx.user_store.get_user(caller_user_id)
    return caller is not None and caller.role == "admin"


async def _caller_owner_id(request: Request, ctx: WebContext) -> str | None:
    """Return the caller's platform user id, or None when unauthenticated.

    When auth is disabled the route may fall back to listing all workflows.
    """
    return getattr(request.state, "platform_user", None) or None


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
                "capabilities": n.capabilities,
                "data": {
                    "label": n.label,
                    **_redact_node_config(n.config),
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
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List workflows visible to the caller."""
    owner_id = await _caller_owner_id(request, ctx)
    is_admin = await _is_admin(request, ctx)
    workflows = await ctx.workflow_store.list_workflows_for_owner(owner_id, is_admin)
    active_map = await ctx.workflow_store.get_active_versions_batch([wf.id for wf in workflows])
    last_exec_map = await ctx.execution_store.get_last_execution_per_workflow([wf.id for wf in workflows])
    result = []
    for wf in workflows:
        api_wf = _workflow_to_api(wf)
        active = active_map.get(wf.id)
        if active is not None:
            api_wf["active_version_id"] = f"{active.workflow_id}:{active.version}"
        last = last_exec_map.get(wf.id)
        if last:
            api_wf["last_execution_status"] = last["status"]
            api_wf["last_execution_at"] = last["created_at"]
        result.append(api_wf)
    return {"workflows": result}


@router.post("/workflows")
async def create_workflow(
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Create a new workflow."""
    name = payload.get("name", "")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name is required and must be a string")

    trigger_type = payload.get("trigger_type", "manual")
    trigger_config = payload.get("trigger_config", {})
    if trigger_type == "webhook" and "secret" not in trigger_config:
        trigger_config = {**trigger_config, "secret": secrets.token_urlsafe(32)}

    owner_id = payload.get("owner_id") or getattr(request.state, "platform_user", "")
    trust_level = payload.get("trust_level", "paranoid")
    if trust_level not in _TRUST_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"trust_level must be one of: {', '.join(sorted(_TRUST_LEVELS))}",
        )

    wf = Workflow(
        id=str(uuid.uuid4()),
        name=name,
        description=payload.get("description", ""),
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        owner_id=owner_id or "",
        trust_level=trust_level,
    )
    await ctx.workflow_store.save_workflow(wf)
    if ctx.trigger_registry is not None:
        await ctx.trigger_registry.reload_one(wf.id)
    # Reveal the webhook secret once on creation so the user can copy it.
    api_wf = _workflow_to_api(wf, redact_secret=False)
    if wf.trigger_type == "webhook" and "has_secret" not in api_wf["trigger_config"]:
        api_wf["trigger_config"]["has_secret"] = bool(wf.trigger_config.get("secret"))
    return api_wf


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Get a workflow by ID."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    api_wf = _workflow_to_api(workflow)
    active = await ctx.workflow_store.get_active_version(workflow_id)
    if active is not None:
        api_wf["active_version_id"] = f"{active.workflow_id}:{active.version}"
    if api_wf["trigger_type"] == "webhook" and api_wf["trigger_config"].get("has_secret"):
        endpoint = api_wf["trigger_config"].get("endpoint") or workflow_id
        api_wf["webhook_url"] = f"{request.base_url}api/webhooks/{endpoint}"
    return api_wf


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    request: Request,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update workflow metadata."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

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
        new_config = dict(payload["trigger_config"])
        # Preserve an existing webhook secret unless the payload explicitly
        # provides a new one, so UI edits don't accidentally clear it. Treat
        # the redacted sentinel as "preserve existing" as well.
        if workflow.trigger_type == "webhook" or new_config.get("trigger_type") == "webhook":
            old_secret = workflow.trigger_config.get("secret")
            if "secret" not in new_config or new_config.get("secret") == REDACTED_SECRET:
                if old_secret:
                    new_config["secret"] = old_secret
                else:
                    new_config.pop("secret", None)
        workflow.trigger_config = new_config
    if "owner_id" in payload:
        workflow.owner_id = payload["owner_id"]
    if "trust_level" in payload:
        trust_level = payload["trust_level"]
        if trust_level not in _TRUST_LEVELS:
            raise HTTPException(
                status_code=422,
                detail=f"trust_level must be one of: {', '.join(sorted(_TRUST_LEVELS))}",
            )
        workflow.trust_level = trust_level

    await ctx.workflow_store.save_workflow(workflow)
    if ctx.trigger_registry is not None:
        await ctx.trigger_registry.reload_one(workflow_id)
    return _workflow_to_api(workflow)


@router.post("/workflows/{workflow_id}/rotate-secret")
async def rotate_workflow_secret(
    workflow_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Rotate the webhook secret for a workflow.

    Returns the new secret once; subsequent list/get/update responses will
    redact it.
    """
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    if workflow.trigger_type != "webhook":
        raise HTTPException(status_code=400, detail="Only webhook workflows have a secret")

    new_secret = secrets.token_urlsafe(32)
    workflow.trigger_config = {**workflow.trigger_config, "secret": new_secret}
    await ctx.workflow_store.save_workflow(workflow)
    if ctx.trigger_registry is not None:
        await ctx.trigger_registry.reload_one(workflow_id)

    api_wf = _workflow_to_api(workflow, redact_secret=False)
    api_wf["trigger_config"]["has_secret"] = True
    return {"workflow": api_wf, "secret": new_secret}


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Delete a workflow and all its versions."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    deleted = await ctx.workflow_store.delete_workflow(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if ctx.trigger_registry is not None:
        await ctx.trigger_registry.reload_one(workflow_id)
    return {"deleted": True}


@router.get("/workflows/{workflow_id}/versions")
async def list_versions(
    workflow_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List all versions for a workflow."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    versions = await ctx.workflow_store.list_versions(workflow_id)
    return {"versions": [_version_to_api(v) for v in versions]}


@router.post("/workflows/{workflow_id}/versions")
async def create_version(
    workflow_id: str,
    request: Request,
    payload: dict[str, Any],
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Save a new version for a workflow."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    existing = await ctx.workflow_store.list_versions(workflow_id)
    next_version = max((v.version for v in existing), default=0) + 1

    nodes_raw = payload.get("nodes", [])
    edges_raw = payload.get("edges", [])

    nodes = [
        WorkflowNode(
            id=n.get("id", str(uuid.uuid4())),
            type=n.get("type", "default"),
            label=n.get("data", {}).get("label", "") if isinstance(n.get("data"), dict) else "",
            config=(
                {k: v for k, v in n.get("data", {}).items() if k != "label"} if isinstance(n.get("data"), dict) else {}
            ),
            position=n.get("position", {"x": 0, "y": 0}),
            capabilities=(n.get("capabilities", []) if isinstance(n.get("capabilities"), list) else []),
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
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Activate a specific version of a workflow.

    version_id is expected to be "{workflow_id}:{version}" or just the version number.
    """
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    # Parse version from version_id
    if ":" in version_id:
        _, version_str = version_id.rsplit(":", 1)
    else:
        version_str = version_id
    try:
        version_num = int(version_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version ID") from exc

    ok = await ctx.workflow_store.activate_version(workflow_id, version_num)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow or version not found")
    return {"activated": True, "version": version_num}


@router.get("/workflows/{workflow_id}/executions")
async def list_executions(
    workflow_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List recent executions for a workflow."""
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    executions = await ctx.execution_store.list_executions(workflow_id, limit=limit)
    return {"executions": executions}


@router.post("/workflows/{workflow_id}/test-run")
async def test_run_workflow(
    workflow_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Execute a test run of a workflow and return the execution result.

    If ``version_id`` is provided in the payload, that specific version is
    executed instead of the active version.
    """
    workflow = await ctx.workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await _require_workflow_access(request, ctx, workflow)

    payload = payload or {}
    version_id = payload.pop("version_id", None)

    if version_id is None:
        version = await ctx.workflow_store.get_active_version(workflow_id)
        if version is None:
            raise HTTPException(status_code=400, detail="No active version")

    executor = WorkflowExecutor(
        ctx.app, execution_store=ctx.execution_store, is_test=True
    )
    result = await executor.execute(
        workflow_id,
        trigger_payload=payload,
        version_id=version_id,
    )

    return {
        "status": result.status,
        "total_elapsed_ms": result.total_elapsed_ms,
        "total_prompt_tokens": result.total_prompt_tokens,
        "total_completion_tokens": result.total_completion_tokens,
        "node_results": [
            {
                "node_id": nr.node_id,
                "status": nr.status,
                "elapsed_ms": nr.elapsed_ms,
                "prompt_tokens": nr.prompt_tokens,
                "completion_tokens": nr.completion_tokens,
                "output": nr.output,
                "error": nr.error,
            }
            for nr in result.node_results
        ],
        "outputs": result.outputs,
    }


@router.get("/dashboard")
async def dashboard(ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    """Return aggregated dashboard data."""
    workflows = await ctx.workflow_store.list_workflows()
    active_count = sum(1 for wf in workflows if wf.trigger_type != "manual")
    recent_executions = await ctx.execution_store.list_recent(limit=5)
    proposal_counts = await ctx.proposal_store.count_by_status()
    pending_proposals = proposal_counts.get("pending", 0)
    auth_status = {
        "telegram": bool(ctx.app.config.telegram.bot_token),
        "matrix": bool(ctx.app.config.matrix.access_token),
        "email": bool(ctx.app.config.email.imap_host),
    }
    platforms_connected = [k for k, v in auth_status.items() if v]
    return {
        "active_workflow_count": active_count,
        "recent_executions": recent_executions,
        "pending_proposal_count": pending_proposals,
        "platforms_connected": platforms_connected,
    }
