"""Tool API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


@router.get("/tools")
async def list_tools(ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    """List all registered tools with their schemas."""
    registry = ctx.app.tool_registry
    schemas = []
    for name in registry.list_names():
        meta = registry.describe(name)
        schemas.append(
            {
                "name": name,
                "description": meta.public_description,
                "parameters": meta.parameters_schema,
                "requires_confirmation": meta.requires_confirmation,
                "tags": meta.tags,
            }
        )
    return {"tools": schemas}
