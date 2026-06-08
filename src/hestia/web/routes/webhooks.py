"""Webhook API routes."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import JSONResponse

from hestia.web.context import WebContext, get_web_context

router = APIRouter()
_CTX_DEP = Depends(get_web_context)

# Replay window in seconds (±5 minutes)
_WEBHOOK_REPLAY_WINDOW = 300

# Bounded LRU cache of recently-seen signature digests
_WEBHOOK_SEEN_MAX_SIZE = 1000
_seen_signatures: OrderedDict[str, None] = OrderedDict()


@router.post("/webhooks/{endpoint}", status_code=202)
async def receive_webhook(
    endpoint: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Receive a webhook payload and publish a webhook_received event.

    Security model:
    - The endpoint must be explicitly configured on a workflow (no wildcard).
    - Requests must include X-Webhook-Timestamp and X-Webhook-Signature.
    - The signature is HMAC-SHA256 over "{timestamp}.{body}".
    - The timestamp must be within ±5 minutes of server time.
    - Workflows without a configured secret are currently un-triggerable
      (empty secrets_list → 401) — fail-closed by design.
    """
    body_bytes = await request.body()

    workflows = await ctx.workflow_store.list_workflows()
    matching = [
        wf
        for wf in workflows
        if wf.trigger_type == "webhook"
        and wf.trigger_config.get("endpoint") == endpoint
    ]
    if not matching:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    secrets_list = [wf.trigger_config.get("secret", "") for wf in matching]
    secrets_list = [s for s in secrets_list if s]

    # Fail-closed: secret-less workflows cannot be triggered
    if not secrets_list:
        raise HTTPException(status_code=401, detail="No secret configured for this endpoint")

    timestamp_header = request.headers.get("X-Webhook-Timestamp", "")
    if not timestamp_header:
        raise HTTPException(status_code=401, detail="Missing X-Webhook-Timestamp header")

    try:
        timestamp = int(timestamp_header)
    except ValueError as _exc:
        raise HTTPException(status_code=401, detail="Invalid X-Webhook-Timestamp header") from _exc

    now = int(time.time())
    if abs(now - timestamp) > _WEBHOOK_REPLAY_WINDOW:
        raise HTTPException(status_code=401, detail="Webhook timestamp outside replay window")

    signature = request.headers.get("X-Webhook-Signature", "")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Webhook-Signature header")

    payload = f"{timestamp}.".encode() + body_bytes
    valid = False
    for secret in secrets_list:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            valid = True
            break

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Replay protection: reject duplicate signatures
    if signature in _seen_signatures:
        raise HTTPException(status_code=409, detail="Duplicate webhook signature")
    _seen_signatures[signature] = None
    if len(_seen_signatures) > _WEBHOOK_SEEN_MAX_SIZE:
        _seen_signatures.popitem(last=False)

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

    # Strip sensitive auth headers before publishing
    safe_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"x-webhook-signature", "authorization", "cookie"}
    }

    await event_bus.publish(
        "webhook_received",
        {
            "endpoint": endpoint,
            "body": body,
            "headers": safe_headers,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    return {"received": True, "endpoint": endpoint}
