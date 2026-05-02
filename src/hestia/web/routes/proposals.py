"""Proposal API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hestia.reflection.types import ProposalStatus
from hestia.web.context import WebContext, get_web_context

router = APIRouter()

_CTX_DEP = Depends(get_web_context)


class RejectBody(BaseModel):
    """Body for reject action."""

    note: str = ""


@router.get("")
async def list_proposals(
    status: ProposalStatus | None = None,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """List proposals by status."""
    proposals = await ctx.proposal_store.list_by_status(status=status)
    return {
        "proposals": [
            {
                "id": p.id,
                "type": p.type,
                "summary": p.summary,
                "evidence": p.evidence,
                "action": p.action,
                "confidence": p.confidence,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "expires_at": p.expires_at.isoformat() if p.expires_at else None,
                "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
                "review_note": p.review_note,
            }
            for p in proposals
        ]
    }


@router.post("/{proposal_id}/accept")
async def accept_proposal(
    proposal_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Accept a proposal."""
    proposal = await ctx.proposal_store.get(proposal_id)
    ok = await ctx.proposal_store.update_status(proposal_id, "accepted")
    if not ok:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if ctx.app.event_bus is not None:
        await ctx.app.event_bus.publish(
            "proposal_approved",
            {
                "proposal_id": proposal_id,
                "proposal_type": proposal.type if proposal is not None else None,
                "platform": "web",
            },
        )
    return {"id": proposal_id, "status": "accepted"}


@router.post("/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    body: RejectBody,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Reject a proposal."""
    proposal = await ctx.proposal_store.get(proposal_id)
    ok = await ctx.proposal_store.update_status(proposal_id, "rejected", review_note=body.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if ctx.app.event_bus is not None:
        await ctx.app.event_bus.publish(
            "proposal_rejected",
            {
                "proposal_id": proposal_id,
                "proposal_type": proposal.type if proposal is not None else None,
                "platform": "web",
            },
        )
    return {"id": proposal_id, "status": "rejected"}


@router.post("/{proposal_id}/defer")
async def defer_proposal(
    proposal_id: str,
    ctx: WebContext = _CTX_DEP,
) -> dict[str, Any]:
    """Defer a proposal."""
    ok = await ctx.proposal_store.update_status(proposal_id, "deferred")
    if not ok:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"id": proposal_id, "status": "deferred"}
