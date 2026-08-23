"""Authentication API routes for the Hestia dashboard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
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


logger = logging.getLogger(__name__)

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

    platform_user = body.get("platform_user")

    client_ip = request.client.host if request.client else "unknown"
    if not auth_manager.check_code_request_limit(client_ip):
        retry_after = auth_manager.code_request_retry_after(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many code requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Record this request
    if client_ip not in auth_manager._code_request_limits:
        auth_manager._code_request_limits[client_ip] = []
    auth_manager._code_request_limits[client_ip].append(datetime.now(UTC))

    try:
        result = await auth_manager.request_code(platform, platform_user)
    except ValueError as exc:
        # SEC-023: don't disclose which platforms/users are configured to
        # anonymous callers; log the specific reason instead.
        logger.warning("Login code request rejected (%s)", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deliver a code for this platform or user.",
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
    result = await auth_manager.validate_code(code, client_ip)

    if result is None:
        # Distinguish rate-limit from invalid code
        if auth_manager.is_rate_limited(client_ip):
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


@router.post("/debug-login")
async def debug_login(
    body: dict[str, Any],
    auth_manager: AuthManager = _AUTH_DEP,
) -> dict[str, Any]:
    """Bypass code verification and create a session directly for a user.

    Only available when web.debug_login is enabled.
    """
    if not auth_manager.config.debug_login:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug login is not enabled",
        )

    user_id = body.get("user_id")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'user_id' is required",
        )

    result = await auth_manager.debug_login(user_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no identities",
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


@router.get("/available-users")
async def available_users(
    auth_manager: AuthManager = _AUTH_DEP,
) -> dict[str, Any]:
    """List users with at least one identity on a running platform.

    SEC-004: this endpoint is unauthenticated (the login page needs it to
    render the user picker), so it returns only what the picker requires:
    user_id and display_name. Roles, platforms, and raw platform_user
    bindings were an unauthenticated reconnaissance feed.
    """
    users = []
    if auth_manager._user_store is not None:
        all_users = await auth_manager._user_store.list_users()
        for user in all_users:
            users.append({
                "user_id": user.id,
                "display_name": user.display_name,
            })
    return {"users": users}


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
                "debug_login": auth_manager.config.debug_login,
                "platform": session.platform,
                "platform_user": session.platform_user,
                "user_id": session.user_id,
            }

    return {
        "authenticated": False,
        "auth_enabled": True,
        "debug_login": auth_manager.config.debug_login,
        "available_platforms": list(auth_manager.adapters.keys()),
    }
