"""Maintenance trace models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class MaintenanceAction:
    """Record of a single memory maintenance action.

    Every merge, prune, and supersede is recorded so operators can review
    what changed and, while within the undo window, restore soft-deleted
    memories.
    """

    id: str
    action: str  # "merge", "prune", "supersede", "undo"
    identity_platform: str | None
    identity_user: str | None
    winner_memory_id: str | None
    loser_memory_ids: list[str]
    reason: str
    created_at: datetime
    undoable_until: datetime
    details: dict[str, Any]
