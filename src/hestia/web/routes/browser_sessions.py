"""Browser session API routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from hestia.tools.browser.session_store import BrowserSessionStore, normalize_domain
from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import require_admin

logger = logging.getLogger(__name__)


async def _run_headed_login(url: str) -> None:
    """Run the headed browser login tool in the background."""
    from hestia.tools.builtin.browser_login import browser_login
    try:
        result = await browser_login(url)
        logger.info("Headed login completed: %s", result)
    except Exception:
        logger.exception("Headed login failed for %s", url)

router = APIRouter()
_CTX_DEP = Depends(get_web_context)


class BrowserSessionOut(BaseModel):
    """Serialized browser session metadata for API responses."""

    domain: str
    has_cookies: bool
    has_storage_state: bool
    cookie_count: int
    last_saved: str | None
    last_used: str | None
    last_health_check: str | None
    health_status: str
    health_check_url: str
    requires_headed: bool


def _session_to_out(
    store: BrowserSessionStore, domain: str
) -> BrowserSessionOut:
    metadata = store.load_metadata(domain)
    session_dir = store._session_dir(domain, create=False)
    has_cookies = (session_dir / "cookies.json").exists()
    has_storage_state = (session_dir / "storage_state.json").exists()
    return BrowserSessionOut(
        domain=domain,
        has_cookies=has_cookies,
        has_storage_state=has_storage_state,
        cookie_count=metadata.cookie_count if metadata else 0,
        last_saved=metadata.last_saved.isoformat() if metadata and metadata.last_saved else None,
        last_used=metadata.last_used.isoformat() if metadata and metadata.last_used else None,
        last_health_check=metadata.last_health_check.isoformat()
        if metadata and metadata.last_health_check
        else None,
        health_status=metadata.health_status if metadata else "unknown",
        health_check_url=metadata.health_check_url if metadata else "",
        requires_headed=metadata.requires_headed if metadata else False,
    )


@router.get("/browser-sessions")
async def list_browser_sessions(
    request: Request, ctx: WebContext = _CTX_DEP
) -> dict[str, Any]:
    """List all browser sessions with metadata."""
    await require_admin(request, ctx)
    store = ctx.browser_session_store
    if store is None:
        raise HTTPException(
            status_code=503, detail="Browser session store not available"
        )
    sessions = store.list_sessions()
    return {
        "sessions": [
            _session_to_out(store, session.domain) for session in sessions
        ]
    }


@router.delete("/browser-sessions/{domain}")
async def delete_browser_session(
    request: Request, domain: str, ctx: WebContext = _CTX_DEP
) -> None:
    """Delete a browser session for the given domain."""
    await require_admin(request, ctx)
    store = ctx.browser_session_store
    if store is None:
        raise HTTPException(
            status_code=503, detail="Browser session store not available"
        )
    domain = normalize_domain(domain)
    store.clear(domain)


@router.post("/browser-sessions/{domain}/check")
async def check_browser_session(
    request: Request,
    domain: str,
    force: bool = False,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, str]:
    """Run a health check on the browser session for the given domain.

    Set ``force=true`` to bypass the automatic once-per-hour rate limit.
    """
    await require_admin(request, ctx)
    store = ctx.browser_session_store
    if store is None:
        raise HTTPException(
            status_code=503, detail="Browser session store not available"
        )
    domain = normalize_domain(domain)
    try:
        status = await store.check_health(domain, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"domain": domain, "status": status}


class RequiresHeadedRequest(BaseModel):
    """Request body to toggle the headed requirement for a domain."""

    requires_headed: bool


@router.patch("/browser-sessions/{domain}/requires-headed")
async def set_requires_headed(
    request: Request,
    domain: str,
    body: RequiresHeadedRequest,
    ctx: WebContext = _CTX_DEP,
) -> BrowserSessionOut:
    """Persist whether this domain needs a headed (visible) browser."""
    await require_admin(request, ctx)
    store = ctx.browser_session_store
    if store is None:
        raise HTTPException(
            status_code=503, detail="Browser session store not available"
        )
    domain = normalize_domain(domain)
    store.update_metadata(domain, requires_headed=body.requires_headed)
    return _session_to_out(store, domain)


class StartBrowserSessionRequest(BaseModel):
    """Request body to start a browser streaming session."""

    url: str
    headed: bool = False


@router.get("/browser-sessions/active")
async def get_active_browser_session(
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Return the active browser streaming session, or None."""
    await require_admin(request, ctx)
    manager = ctx.stream_manager
    if manager is None:
        raise HTTPException(
            status_code=503, detail="Stream manager not available"
        )
    active = manager.get_active_session()
    return {"active": active}


@router.post("/browser-sessions/start")
async def start_browser_session(
    request: Request,
    body: StartBrowserSessionRequest,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Start a new browser streaming session."""
    await require_admin(request, ctx)
    manager = ctx.stream_manager
    if manager is None:
        raise HTTPException(
            status_code=503, detail="Stream manager not available"
        )
    if manager.is_active():
        active_id = manager.get_session_id()
        raise HTTPException(
            status_code=409,
            detail={"error": "Session already active", "session_id": active_id},
        )

    session_id = await manager.start(body.url, headed=body.headed)
    session = manager.get_active_session()
    return {
        "session_id": session_id,
        "domain": session.get("domain", "") if session else "",
        "url": session.get("url", body.url) if session else body.url,
        "ws_url": f"/api/browser-session/stream/{session_id}",
    }


@router.post("/browser-sessions/stop")
async def stop_browser_session(
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Stop the active browser streaming session."""
    await require_admin(request, ctx)
    manager = ctx.stream_manager
    if manager is None:
        raise HTTPException(
            status_code=503, detail="Stream manager not available"
        )
    if not manager.is_active():
        raise HTTPException(status_code=404, detail="No active session")

    session_id = manager.get_session_id()
    if session_id is None:
        raise HTTPException(status_code=404, detail="No active session")
    summary = await manager.stop(session_id)
    return summary


@router.post("/browser-sessions/restart-headed")
async def restart_headed_browser_session(
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Restart the active stream in headed (visible) mode.

    Preserves the WebSocket session ID so connected clients keep receiving
    frames after the browser relaunches.
    """
    await require_admin(request, ctx)
    manager = ctx.stream_manager
    if manager is None:
        raise HTTPException(
            status_code=503, detail="Stream manager not available"
        )
    if not manager.is_active():
        raise HTTPException(status_code=404, detail="No active session")

    session_id = manager.get_session_id()
    if session_id is None:
        raise HTTPException(status_code=404, detail="No active session")
    await manager.restart_headed(session_id)
    session = manager.get_active_session()
    return {
        "session_id": session_id,
        "domain": session.get("domain", "") if session else "",
        "url": session.get("url", "") if session else "",
        "ws_url": f"/api/browser-session/stream/{session_id}",
    }


@router.post("/browser-sessions/headed-login")
async def headed_browser_login(
    request: Request,
    body: StartBrowserSessionRequest,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, str]:
    """Launch a headed (visible) browser for manual login.

    Runs in the background so the HTTP response returns immediately.
    The user must log in and close the browser window on the server
    to save the session.
    """
    await require_admin(request, ctx)
    parsed = normalize_domain(body.url)
    if not parsed:
        raise HTTPException(status_code=400, detail="Invalid URL")
    asyncio.create_task(_run_headed_login(body.url))
    return {
        "message": f"Headed browser launched for {body.url}. "
        "Log in and close the window to save the session."
    }


@router.websocket("/browser-session/stream/{session_id}")
async def browser_stream_ws(
    websocket: WebSocket, session_id: str
) -> None:
    """WebSocket endpoint for bidirectional browser stream."""
    # Auth check before accept
    auth_header = websocket.headers.get("Authorization", "")
    token: str | None = (
        auth_header[7:] if auth_header.startswith("Bearer ") else websocket.query_params.get("token")
    )

    ctx = get_web_context()
    if ctx.auth_manager is not None:
        status, web_session = ctx.auth_manager.validate_token(token or "")
        if status != "valid":
            await websocket.close(
                code=1008, reason="Authentication required"
            )
            return
        user_id = web_session.user_id if web_session is not None else None
        if user_id is None:
            await websocket.close(
                code=1008, reason="Admin access required"
            )
            return
        user = await ctx.user_store.get_user(user_id)
        if user is None or user.role != "admin":
            await websocket.close(
                code=1008, reason="Admin access required"
            )
            return

    manager = ctx.stream_manager
    if manager is None or manager.get_session_id() != session_id:
        active_id = manager.get_session_id() if manager else None
        logger.warning(
            "WS rejected: session %s not found (active=%s)", session_id, active_id
        )
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    logger.info("WS accepted for session %s", session_id)

    stream_session = manager._session
    assert stream_session is not None
    stream_session.ws_clients.add(websocket)

    try:
        while True:
            message = await websocket.receive_text()
            logger.debug("WS received message for session %s", session_id)
            event = json.loads(message)
            await manager.forward_input(session_id, event)
    except WebSocketDisconnect:
        logger.info("WS client disconnected for session %s", session_id)
    finally:
        stream_session.ws_clients.discard(websocket)
        logger.info("WS client removed for session %s", session_id)
