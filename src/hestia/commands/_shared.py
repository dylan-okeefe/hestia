"""Shared helpers used by multiple command modules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _format_datetime(dt: datetime | None) -> str:
    """Format a datetime for display in the CLI."""
    if dt is None:
        return "N/A"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _parse_since(since: str) -> datetime:
    """Convert a human-readable window like '7d' or '24h' to a datetime."""
    now = datetime.now(UTC)
    if since.endswith("d"):
        days = int(since[:-1])
        return now - timedelta(days=days)
    if since.endswith("h"):
        hours = int(since[:-1])
        return now - timedelta(hours=hours)
    # fallback: assume days
    return now - timedelta(days=int(since))
