"""On-demand blocked-actions summary tool."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from hestia.core.clock import utcnow
from hestia.tools.metadata import tool

if TYPE_CHECKING:
    from hestia.blocked_actions.digest import BlockedActionsDigest


DEFAULT_WINDOW_HOURS = 24


def make_blocked_actions_summary_tool(
    digest: BlockedActionsDigest,
) -> Any:
    """Return the blocked_actions_summary tool bound to a digest service."""

    @tool(
        name="blocked_actions_summary",
        public_description="Show a summary of actions the trust gate blocked or escalated.",
        internal_description="",
        parameters_schema={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Lookback window in hours (default 24)",
                },
            },
        },
    )
    async def blocked_actions_summary(hours: int = DEFAULT_WINDOW_HOURS) -> str:
        """Return a human-readable summary of recent blocked/escalated actions."""
        since = utcnow() - timedelta(hours=hours)
        events = await digest.query(since=since)
        text = digest.format_digest(events, title="Blocked actions summary")
        if text is None:
            return "No blocked or escalated actions in the requested window."
        return text

    return blocked_actions_summary
