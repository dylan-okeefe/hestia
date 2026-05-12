"""Webhook API routes."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse

from hestia.web.context import WebContext, get_web_context

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


@router.post("/webhooks/{endpoint}", status_code=202)
async def receive_webhook(
    endpoint: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Receive a webhook payload and publish a webhook_received event."""
    body_bytes = await request.body()

    workflows = await ctx.workflow_store.list_workflows()
    matching = [
        wf
        for wf in workflows
        if wf.trigger_type == "webhook"
        and (
            wf.trigger_config.get("endpoint") == endpoint
            or wf.trigger_config.get("endpoint") is None
        )
    ]
    if not matching:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    secrets_list = [wf.trigger_config.get("secret", "") for wf in matching]
    secrets_list = [s for s in secrets_list if s]

    signature = request.headers.get("X-Webhook-Signature", "")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Webhook-Signature header")

    valid = False
    for secret in secrets_list:
        expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            valid = True
            break

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = json.loads(body_bytes)
    except Exception:
        body = body_bytes.decode("utf-8")

    event_bus = ctx.app.event_bus
    if event_bus is None:
        return JSONResponse(
            {"detail": "Event bus unavailable"},
            status_code=503,
        )

    await event_bus.publish(
        "webhook_received",
        {
            "endpoint": endpoint,
            "body": body,
            "headers": dict(request.headers),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    return {"received": True, "endpoint": endpoint}
