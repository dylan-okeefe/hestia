"""Dataclasses for the reflection loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

ProposalType = Literal["identity_update", "new_chain", "tool_fix", "policy_tweak"]
ProposalStatus = Literal["pending", "accepted", "rejected", "deferred", "expired"]


@dataclass
class Observation:
    """A structured observation mined from traces."""

    category: Literal["frustration", "correction", "slow_turn", "repeated_chain", "tool_failure"]
    turn_id: str
    description: str
    confidence: float


@dataclass
class Proposal:
    """A concrete proposal generated from observations."""

    id: str
    type: ProposalType
    summary: str
    evidence: list[str]  # turn IDs
    action: dict[str, Any]  # action-specific payload
    confidence: float
    status: ProposalStatus
    created_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None = None
    review_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "id": self.id,
            "type": self.type,
            "summary": self.summary,
            "evidence": self.evidence,
            "action": self.action,
            "confidence": self.confidence,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_note": self.review_note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Proposal:
        """Deserialize from a dict."""
        return cls(
            id=data["id"],
            type=data["type"],
            summary=data["summary"],
            evidence=data["evidence"],
            action=data["action"],
            confidence=data["confidence"],
            status=data["status"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            review_note=data.get("review_note"),
        )
