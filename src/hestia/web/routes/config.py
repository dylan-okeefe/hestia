"""Config API routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Depends

from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


def _mask_secrets(obj: Any) -> Any:
    """Recursively mask sensitive fields in config dicts."""
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if key in ("bot_token", "access_token", "password", "password_env", "api_key"):
                result[key] = "***" if value else ""
            else:
                result[key] = _mask_secrets(value)
        return result
    if isinstance(obj, list):
        return [_mask_secrets(item) for item in obj]
    return obj


@router.get("/config")
async def get_config(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Return running configuration with secrets masked."""
    raw = asdict(ctx.app.config)
    return cast(dict[str, Any], _mask_secrets(raw))


@router.put("/config")
async def put_config(
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Update configuration — not yet implemented."""
    return {"detail": "Config updates are not yet implemented"}
