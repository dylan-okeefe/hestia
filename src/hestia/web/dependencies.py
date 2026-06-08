"""Shared FastAPI dependencies for authorization."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from hestia.web.context import WebContext, get_web_context


async def require_admin(
    request: Request,
    ctx: WebContext = Depends(get_web_context),
) -> None:
    """Raise 401/403 if the caller is not an admin."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        auth_enabled = getattr(
            ctx.app.config.features.web, "auth_enabled", True
        )
        if auth_enabled:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return

    user = await ctx.user_store.get_user(user_id)
    if user is None or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def get_current_platform_user(request: Request) -> str | None:
    """Return the current platform user from request state."""
    return getattr(request.state, "platform_user", None)


class RequireOwner:
    """Dependency factory that enforces resource ownership."""

    def __init__(self, resource_platform_user: str) -> None:
        self.resource_platform_user = resource_platform_user

    async def __call__(
        self,
        request: Request,
        ctx: WebContext = Depends(get_web_context),
    ) -> None:
        """Raise 403 if the caller does not own the resource (unless admin)."""
        caller_platform_user = getattr(request.state, "platform_user", None)
        if caller_platform_user is None:
            auth_enabled = getattr(
                ctx.app.config.features.web, "auth_enabled", True
            )
            if auth_enabled:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return
        if caller_platform_user == self.resource_platform_user:
            return

        user_id = getattr(request.state, "user_id", None)
        if user_id is not None:
            user = await ctx.user_store.get_user(user_id)
            if user is not None and user.role == "admin":
                return

        raise HTTPException(status_code=403, detail="Access denied")
