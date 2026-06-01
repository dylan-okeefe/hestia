"""Browser session API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hestia.tools.browser.session_store import BrowserSessionStore

router = APIRouter()


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
    )


@router.get("/browser-sessions")
async def list_browser_sessions() -> dict[str, Any]:
    """List all browser sessions with metadata."""
    store = BrowserSessionStore()
    sessions = store.list_sessions()
    return {
        "sessions": [
            _session_to_out(store, session.domain) for session in sessions
        ]
    }


@router.delete("/browser-sessions/{domain}")
async def delete_browser_session(domain: str) -> None:
    """Delete a browser session for the given domain."""
    store = BrowserSessionStore()
    store.clear(domain)


@router.post("/browser-sessions/{domain}/check")
async def check_browser_session(domain: str) -> dict[str, str]:
    """Run a health check on the browser session for the given domain."""
    store = BrowserSessionStore()
    try:
        status = await store.check_health(domain)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"domain": domain, "status": status}
