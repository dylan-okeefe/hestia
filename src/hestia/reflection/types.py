"""Dataclasses for the reflection loop."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

ProposalType = Literal["identity_update", "new_chain", "tool_fix", "policy_tweak"]
ProposalStatus = Literal["pending", "accepted", "rejected", "deferred", "expired"]


@dataclass
class Proposal:
    id: str
    type: ProposalType
    summary: str
    evidence: list[str]
    action: dict[str, Any]
    confidence: float
    status: ProposalStatus
    created_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None = None
    review_note: str | None = None
