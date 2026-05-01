"""Authentication API routes for the Hestia dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from hestia.web.auth import AuthManager
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


def _get_auth_manager(ctx: WebContext = _CTX_DEP) -> AuthManager:
    if ctx.auth_manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth manager not configured",
        )
    return ctx.auth_manager


_AUTH_DEP = Depends(_get_auth_manager)


@router.post("/request-code")
async def request_code(
    body: dict[str, Any],
    request: Request,
    auth_manager: AuthManager = _AUTH_DEP,
) -> dict[str, Any]:
    """Request a one-time authentication code via a chat platform."""
    platform = body.get("platform")
    if not platform or not isinstance(platform, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'platform' is required",
        )

    client_ip = request.client.host if request.client else "unknown"
    if not auth_manager.check_code_request_limit(client_ip):
        retry_after = auth_manager.code_request_retry_after(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many code requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Record this request
    from datetime import datetime, UTC
    if client_ip not in auth_manager._code_request_limits:
        auth_manager._code_request_limits[client_ip] = []
    auth_manager._code_request_limits[client_ip].append(datetime.now(UTC))

    try:
        result = await auth_manager.request_code(platform)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return result


@router.post("/verify-code")
async def verify_code(
    body: dict[str, Any],
    request: Request,
    auth_manager: AuthManager = _AUTH_DEP,
) -> dict[str, Any]:
    """Verify a one-time code and create a session."""
    code = body.get("code", "")
    if not code or not isinstance(code, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid code",
        )

    client_ip = request.client.host if request.client else "unknown"
    result = auth_manager.validate_code(code, client_ip)

    if result is None:
        # Distinguish rate-limit from invalid code
        if auth_manager._is_rate_limited(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Try again later.",
                headers={"Retry-After": str(600)},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired code",
        )

    token, session = result

    return {
        "token": token,
        "platform": session.platform,
        "platform_user": session.platform_user,
        "expires_at": session.expires_at.isoformat(),
    }


@router.post("/logout")
async def logout(
    request: Request,
    auth_manager: AuthManager = _AUTH_DEP,
) -> dict[str, Any]:
    """Log out the current session."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        auth_manager.remove_session(token)

    return {"status": "ok"}


@router.get("/status")
async def auth_status(
    request: Request,
    auth_manager: AuthManager = _AUTH_DEP,
) -> dict[str, Any]:
    """Return the current authentication status."""
    if not auth_manager.config.auth_enabled:
        return {"authenticated": True, "auth_enabled": False}

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        status_code, session = auth_manager.validate_token(token)
        if status_code == "valid":
            assert session is not None
            return {
                "authenticated": True,
                "auth_enabled": True,
                "platform": session.platform,
                "platform_user": session.platform_user,
            }

    return {
        "authenticated": False,
        "auth_enabled": True,
        "available_platforms": list(auth_manager.adapters.keys()),
    }
