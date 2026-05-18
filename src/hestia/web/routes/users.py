"""User and room management API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from hestia.web.context import WebContext, get_web_context
from hestia.web.dependencies import require_admin

router = APIRouter()
_CTX_DEP = Depends(get_web_context)

_ROLES = {"admin", "trusted", "user", "child"}
_TRUST_PRESETS = {"paranoid", "household", "developer"}


# User CRUD


@router.get("/users")
async def list_users(ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    users = await ctx.user_store.list_users()
    result = []
    for u in users:
        identities = await ctx.user_store.get_identities(u.id)
        rooms = await ctx.user_store.get_user_rooms(u.id)
        result.append(
            {
                "id": u.id,
                "display_name": u.display_name,
                "role": u.role,
                "trust_preset": u.trust_preset,
                "notes": u.notes,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "identity_count": len(identities),
                "room_count": len(rooms),
            }
        )
    return {"users": result}


@router.post("/users")
async def create_user(
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    display_name = payload.get("display_name", "")
    if not display_name or not isinstance(display_name, str):
        raise HTTPException(status_code=400, detail="display_name is required")

    role = payload.get("role", "user")
    if role not in _ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"role must be one of: {', '.join(sorted(_ROLES))}",
        )

    trust_preset = payload.get("trust_preset")
    if trust_preset is not None and trust_preset not in _TRUST_PRESETS:
        raise HTTPException(
            status_code=422,
            detail=f"trust_preset must be one of: {', '.join(sorted(_TRUST_PRESETS))}",
        )

    user = await ctx.user_store.create_user(
        display_name=display_name,
        role=role,
        trust_preset=trust_preset,
        notes=payload.get("notes"),
    )
    return {
        "id": user.id,
        "display_name": user.display_name,
        "role": user.role,
        "trust_preset": user.trust_preset,
        "notes": user.notes,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/users/{user_id}")
async def get_user(user_id: str, ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    user = await ctx.user_store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    identities = await ctx.user_store.get_identities(user_id)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "role": user.role,
        "trust_preset": user.trust_preset,
        "notes": user.notes,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "identities": [
            {
                "platform": i.platform,
                "platform_user": i.platform_user,
                "verified": i.verified,
            }
            for i in identities
        ],
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    user = await ctx.user_store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    fields: dict[str, Any] = {}
    if "display_name" in payload:
        fields["display_name"] = payload["display_name"]
    if "role" in payload:
        role = payload["role"]
        if role not in _ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"role must be one of: {', '.join(sorted(_ROLES))}",
            )
        fields["role"] = role
    if "trust_preset" in payload:
        tp = payload["trust_preset"]
        if tp is not None and tp not in _TRUST_PRESETS:
            raise HTTPException(
                status_code=422,
                detail=f"trust_preset must be one of: {', '.join(sorted(_TRUST_PRESETS))}",
            )
        fields["trust_preset"] = tp
    if "notes" in payload:
        fields["notes"] = payload["notes"]

    updated = await ctx.user_store.update_user(user_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": updated.id,
        "display_name": updated.display_name,
        "role": updated.role,
        "trust_preset": updated.trust_preset,
        "notes": updated.notes,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    deleted = await ctx.user_store.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deleted": True}


# Identity management


@router.post("/users/{user_id}/identities")
async def add_identity(
    user_id: str,
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    platform = payload.get("platform", "")
    platform_user = payload.get("platform_user", "")
    if not platform or not platform_user:
        raise HTTPException(
            status_code=400, detail="platform and platform_user are required"
        )

    await ctx.user_store.add_identity(user_id, platform, platform_user)
    return {"added": True, "platform": platform, "platform_user": platform_user}


@router.delete("/users/{user_id}/identities/{platform}/{platform_user}")
async def remove_identity(
    user_id: str,
    platform: str,
    platform_user: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    removed = await ctx.user_store.remove_identity(platform, platform_user)
    if not removed:
        raise HTTPException(status_code=404, detail="Identity not found")
    return {"removed": True}


@router.get("/users/{user_id}/handoffs")
async def get_user_handoffs(
    user_id: str,
    ctx: WebContext = _CTX_DEP,
) -> list[dict[str, Any]]:
    """Return the last 3 handoff summaries for a user's platform identities."""
    user = await ctx.user_store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    identities = await ctx.user_store.get_identities(user_id)
    identity_tuples = [
        (i.platform, i.platform_user) for i in identities
    ]

    handoffs = await ctx.session_store.list_handoffs_for_identities(
        identity_tuples, limit=3
    )
    return handoffs


# Room routes


@router.get("/rooms")
async def list_rooms(ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    rooms = await ctx.user_store.list_rooms()
    return {
        "rooms": [
            {
                "id": r.id,
                "platform": r.platform,
                "platform_room_id": r.platform_room_id,
                "display_name": r.display_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rooms
        ]
    }


@router.get("/rooms/{room_id}")
async def get_room(room_id: str, ctx: WebContext = _CTX_DEP) -> dict[str, Any]:
    room = await ctx.user_store.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    members = await ctx.user_store.get_room_members(room_id)
    return {
        "id": room.id,
        "platform": room.platform,
        "platform_room_id": room.platform_room_id,
        "display_name": room.display_name,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "members": [
            {"id": m.id, "display_name": m.display_name, "role": m.role}
            for m in members
        ],
    }


@router.put("/rooms/{room_id}")
async def update_room(
    room_id: str,
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    room = await ctx.user_store.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    fields: dict[str, Any] = {}
    if "display_name" in payload:
        fields["display_name"] = payload["display_name"]
    updated = await ctx.user_store.update_room(room_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"id": updated.id, "display_name": updated.display_name}


@router.get("/rooms/{room_id}/members")
async def list_room_members(
    room_id: str, ctx: WebContext = _CTX_DEP
) -> dict[str, Any]:
    room = await ctx.user_store.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    members = await ctx.user_store.get_room_members(room_id)
    return {
        "members": [
            {"id": m.id, "display_name": m.display_name, "role": m.role}
            for m in members
        ]
    }


@router.post("/rooms/{room_id}/members")
async def add_room_member(
    room_id: str,
    payload: dict[str, Any],
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    user_id = payload.get("user_id", "")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    await ctx.user_store.add_room_member(room_id, user_id)
    return {"added": True}


@router.delete("/rooms/{room_id}/members/{user_id}")
async def remove_room_member(
    room_id: str,
    user_id: str,
    request: Request,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    await require_admin(request, ctx)
    removed = await ctx.user_store.remove_room_member(room_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"removed": True}
