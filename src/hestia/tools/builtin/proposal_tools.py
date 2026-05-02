"""Proposal tools — list, show, accept, reject, defer reflection proposals."""

from collections.abc import Callable, Coroutine
from typing import Any

from hestia.reflection.store import ProposalStore
from hestia.reflection.types import ProposalStatus
from hestia.tools.capabilities import SELF_MANAGEMENT
from hestia.tools.metadata import tool

if __import__("typing").TYPE_CHECKING:
    from hestia.events.bus import EventBus


def make_list_proposals_tool(
    proposal_store: ProposalStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a list_proposals tool bound to a ProposalStore instance."""

    @tool(
        name="list_proposals",
        public_description="List reflection proposals. Params: status (str, default 'pending').",
        tags=["proposal", "builtin"],
        capabilities=[SELF_MANAGEMENT],
    )
    async def list_proposals(status: str = "pending") -> str:
        """List reflection proposals filtered by status.

        Args:
            status: Filter by status — pending, accepted, rejected, deferred, expired

        Returns:
            Formatted list of proposals with IDs, types, summaries, and dates.
        """
        valid_statuses: set[ProposalStatus] = {
            "pending", "accepted", "rejected", "deferred", "expired",
        }
        if status not in valid_statuses:
            return f"Invalid status '{status}'. Valid: {', '.join(sorted(valid_statuses))}"

        proposals = await proposal_store.list_by_status(status=status, limit=100)
        if not proposals:
            return f"No {status} proposals found."

        lines = []
        for p in proposals:
            date = p.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{p.id}] ({date}) {p.type}: {p.summary}")
        return "\n".join(lines)

    return list_proposals


def make_show_proposal_tool(
    proposal_store: ProposalStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a show_proposal tool bound to a ProposalStore instance."""

    @tool(
        name="show_proposal",
        public_description="Show full details of a proposal. Params: proposal_id (str).",
        tags=["proposal", "builtin"],
        capabilities=[SELF_MANAGEMENT],
    )
    async def show_proposal(proposal_id: str) -> str:
        """Show full details of a single proposal.

        Args:
            proposal_id: The proposal ID to look up

        Returns:
            Formatted proposal details or a not-found message.
        """
        p = await proposal_store.get(proposal_id)
        if p is None:
            return f"No proposal with id {proposal_id}"

        lines = [
            f"ID: {p.id}",
            f"Type: {p.type}",
            f"Summary: {p.summary}",
            f"Confidence: {p.confidence}",
            f"Status: {p.status}",
            f"Created: {p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else 'N/A'}",
            f"Expires: {p.expires_at.strftime('%Y-%m-%d %H:%M') if p.expires_at else 'N/A'}",
        ]
        if p.evidence:
            lines.append(f"Evidence: {', '.join(p.evidence)}")
        if p.action:
            lines.append(f"Action: {p.action}")
        if p.reviewed_at:
            lines.append(f"Reviewed: {p.reviewed_at.strftime('%Y-%m-%d %H:%M')}")
        if p.review_note:
            lines.append(f"Review note: {p.review_note}")
        return "\n".join(lines)

    return show_proposal


def make_accept_proposal_tool(
    proposal_store: ProposalStore,
    event_bus: "EventBus | None" = None,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create an accept_proposal tool bound to a ProposalStore instance."""

    @tool(
        name="accept_proposal",
        public_description=(
            "Accept a reflection proposal. Params: proposal_id (str), note (str, optional)."
        ),
        tags=["proposal", "builtin"],
        capabilities=[SELF_MANAGEMENT],
        requires_confirmation=True,
    )
    async def accept_proposal(proposal_id: str, note: str | None = None) -> str:
        """Accept a reflection proposal.

        Args:
            proposal_id: The proposal ID to accept
            note: Optional review note

        Returns:
            Confirmation or error message.
        """
        proposal = await proposal_store.get(proposal_id)
        ok = await proposal_store.update_status(proposal_id, "accepted", review_note=note)
        if not ok:
            return f"No proposal with id {proposal_id}"
        if event_bus is not None:
            await event_bus.publish(
                "proposal_approved",
                {
                    "proposal_id": proposal_id,
                    "proposal_type": proposal.type if proposal is not None else None,
                    "platform": "tool",
                },
            )
        return f"Accepted proposal {proposal_id}"

    return accept_proposal


def make_reject_proposal_tool(
    proposal_store: ProposalStore,
    event_bus: "EventBus | None" = None,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a reject_proposal tool bound to a ProposalStore instance."""

    @tool(
        name="reject_proposal",
        public_description=(
            "Reject a reflection proposal. Params: proposal_id (str), note (str, optional)."
        ),
        tags=["proposal", "builtin"],
        capabilities=[SELF_MANAGEMENT],
        requires_confirmation=True,
    )
    async def reject_proposal(proposal_id: str, note: str | None = None) -> str:
        """Reject a reflection proposal.

        Args:
            proposal_id: The proposal ID to reject
            note: Optional review note

        Returns:
            Confirmation or error message.
        """
        proposal = await proposal_store.get(proposal_id)
        ok = await proposal_store.update_status(proposal_id, "rejected", review_note=note)
        if not ok:
            return f"No proposal with id {proposal_id}"
        if event_bus is not None:
            await event_bus.publish(
                "proposal_rejected",
                {
                    "proposal_id": proposal_id,
                    "proposal_type": proposal.type if proposal is not None else None,
                    "platform": "tool",
                },
            )
        return f"Rejected proposal {proposal_id}"

    return reject_proposal


def make_defer_proposal_tool(
    proposal_store: ProposalStore,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create a defer_proposal tool bound to a ProposalStore instance."""

    @tool(
        name="defer_proposal",
        public_description="Defer a reflection proposal. Params: proposal_id (str).",
        tags=["proposal", "builtin"],
        capabilities=[SELF_MANAGEMENT],
    )
    async def defer_proposal(proposal_id: str) -> str:
        """Defer a reflection proposal.

        Args:
            proposal_id: The proposal ID to defer

        Returns:
            Confirmation or error message.
        """
        ok = await proposal_store.update_status(proposal_id, "deferred")
        if not ok:
            return f"No proposal with id {proposal_id}"
        return f"Deferred proposal {proposal_id}"

    return defer_proposal
