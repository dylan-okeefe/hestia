"""Centralized time utilities.

All internal timestamps are UTC. Local time is only used at display boundaries.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return timezone-aware UTC now. Use this everywhere instead of datetime.now()."""
    return datetime.now(tz=UTC)
